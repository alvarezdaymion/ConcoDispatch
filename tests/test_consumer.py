"""Subprocess regression tests; all captures and Hermes responses are synthetic."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONSUMER = ROOT / "voice_kanban" / "consumer.py"


def envelope(capture_id: str, transcript: str, marker: str = "VOICEKANBAN/2") -> bytes:
    return (f"{marker}\ncapture_id: {capture_id}\n"
            f"captured_at: 2026-01-01T10:00:00Z\n---\n{transcript}\n").encode()


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".local"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.queue = self.root / "queue"
        self.queue.mkdir()
        self.state = self.root / "state"
        self.calls = self.root / "calls.jsonl"
        self.hermes = self.root / "hermes"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("VOICE_KANBAN_")}
        self.env.update(VOICE_KANBAN_HERMES_BIN=str(self.hermes),
                        VOICE_KANBAN_QUEUE_DIR=str(self.queue),
                        VOICE_KANBAN_STATE_DIR=str(self.state),
                        VOICE_KANBAN_NOTIFY_TARGET="")
        self.stub()

    def stub(self, behavior=""):
        self.hermes.write_text(
            f"#!{sys.executable}\nimport json, sys\nfrom pathlib import Path\n"
            f"root = Path({str(self.root)!r})\n"
            "args = sys.argv[1:]\n"
            "creating = args[:2] == ['kanban', 'create']\n"
            "if creating and not list((root / 'state' / 'archive').glob('*.txt')):\n"
            "    raise SystemExit('archive missing before create')\n"
            "with (root / 'calls.jsonl').open('a') as stream:\n"
            "    stream.write(json.dumps(args) + '\\n')\n"
            + behavior + "\n"
            "print(json.dumps({'id': 't_synthetic'} if creating else {'ok': True}))\n"
        )
        self.hermes.chmod(0o700)

    def capture(self, capture_id="capture-synthetic-0001", text="Draft a project outline", marker="VOICEKANBAN/2"):
        source = self.queue / f"{capture_id}.txt"
        source.write_bytes(envelope(capture_id, text, marker))
        return source

    def run_consumer(self, code=0):
        result = subprocess.run([sys.executable, str(CONSUMER)], env=self.env,
                                capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, code, result.stderr)
        return result

    def recorded(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def receipt(self, fields="status, task_id, notified_at"):
        with sqlite3.connect(self.state / "receipts.sqlite3") as db:
            return db.execute(f"SELECT {fields} FROM captures").fetchone()

    def test_archive_before_idempotent_create_and_optional_receipt(self):
        self.env["VOICE_KANBAN_NOTIFY_TARGET"] = "test-channel"
        source = self.capture()
        payload = source.read_bytes()
        self.run_consumer()
        self.run_consumer()
        self.assertFalse(source.exists())
        self.assertEqual((self.state / "archive" / source.name).read_bytes(), payload)
        create, notification = self.recorded()
        self.assertEqual(create[:3], ["kanban", "create", "Draft a project outline"])
        self.assertEqual(create[create.index("--assignee") + 1], "default")
        self.assertEqual(create[create.index("--idempotency-key") + 1],
                         f"iphone-voice-capture:{source.stem}")
        self.assertEqual(create[-1], "--json")
        self.assertEqual(notification[:3], ["send", "--to", "test-channel"])
        self.assertIn("t_synthetic", notification[3])
        self.assertEqual(self.receipt()[:2], ("confirmed", "t_synthetic"))
        self.assertIsNotNone(self.receipt()[2])

    def test_uncertain_create_reuses_idempotency_key(self):
        self.stub("if creating and not (root / 'attempted').exists():\n"
                  "    (root / 'attempted').touch()\n"
                  "    print('response lost')\n"
                  "    raise SystemExit(0)\n")
        source = self.capture()
        self.run_consumer(1)
        self.assertTrue(source.exists())
        self.assertTrue((self.state / "archive" / source.name).exists())
        self.run_consumer()
        keys = [a[a.index("--idempotency-key") + 1] for a in self.recorded()]
        self.assertEqual(keys, [f"iphone-voice-capture:{source.stem}"] * 2)
        self.assertEqual(self.receipt("status, task_id, attempts"),
                         ("confirmed", "t_synthetic", 2))

    def test_legacy_plain_text_is_recovered_without_rename(self):
        source = self.queue / ".txt-7.txt"
        payload = b"Review the synthetic project outline\n"
        source.write_bytes(payload)
        self.run_consumer()
        create, = self.recorded()
        self.assertEqual(create[2], payload.decode().strip())
        key = create[create.index("--idempotency-key") + 1]
        self.assertRegex(key, r"^iphone-voice-capture:legacy-[0-9a-f]{64}$")
        self.assertEqual((self.state / "archive" / (key.split(":", 1)[1] + ".txt")).read_bytes(), payload)
        self.assertEqual(list(self.queue.iterdir()), [])

    def test_locale_formatted_random_number_is_valid(self):
        source = self.capture("capture-20260101T100000123-482,901,337")
        self.run_consumer()
        self.assertTrue((self.state / "archive" / source.name).exists())

    def test_ten_capture_burst_and_duplicate_replay_create_ten_cards(self):
        sources = [self.capture(f"capture-synthetic-{index:04d}", f"Synthetic note {index}")
                   for index in range(10)]
        duplicate = sources[4]
        payload = duplicate.read_bytes()
        self.run_consumer()
        duplicate.write_bytes(payload)
        self.run_consumer()
        calls = self.recorded()
        self.assertEqual(len(calls), 10)
        self.assertTrue(all(a[:2] == ["kanban", "create"] for a in calls))
        self.assertEqual(len({a[a.index("--idempotency-key") + 1] for a in calls}), 10)
        self.assertEqual(len(list((self.state / "archive").glob("*.txt"))), 10)
        self.assertEqual(self.receipt("COUNT(*)"), (10,))
        self.assertEqual(list(self.queue.iterdir()), [])

    def test_notification_retries_from_archive_when_source_disappears(self):
        self.env["VOICE_KANBAN_NOTIFY_TARGET"] = "test-channel"
        self.stub("if not creating and not (root / 'send-attempted').exists():\n"
                  "    (root / 'send-attempted').touch()\n"
                  "    raise SystemExit(1)\n")
        source = self.capture()
        self.run_consumer(1)
        self.assertEqual(self.receipt(), ("confirmed", "t_synthetic", None))
        source.unlink()
        self.run_consumer()
        calls = self.recorded()
        self.assertEqual(sum(a[:2] == ["kanban", "create"] for a in calls), 1)
        self.assertEqual(sum(a[:2] == ["send", "--to"] for a in calls), 2)
        self.assertIsNotNone(self.receipt()[2])

    def test_filename_mismatch_archived_and_rejected_before_create(self):
        source = self.capture()
        payload = source.read_bytes()
        moved = source.with_name("capture-wrong-name.txt")
        source.rename(moved)
        result = self.run_consumer(1)
        self.assertIn("does not match payload", result.stderr)
        self.assertTrue(moved.exists())
        self.assertFalse(self.calls.exists())
        self.assertEqual((self.state / "archive" / source.name).read_bytes(), payload)

    def test_source_changed_after_archive_is_not_deleted(self):
        source = self.capture()
        original = source.read_bytes()
        replacement = envelope(source.stem, "Replacement note must survive")
        self.stub(f"(root / 'queue' / {source.name!r}).write_bytes({replacement!r})\n")
        result = self.run_consumer(1)
        self.assertIn("changed after local archival", result.stderr)
        self.assertEqual(source.read_bytes(), replacement)
        self.assertEqual((self.state / "archive" / source.name).read_bytes(), original)
        self.assertEqual(self.receipt()[:2], ("confirmed", "t_synthetic"))

    def test_configured_envelope_marker_preserves_capture_identity(self):
        self.env["VOICE_KANBAN_ENVELOPE_MARKER"] = "LOCALVOICE/2"
        source = self.capture(marker="LOCALVOICE/2")
        self.run_consumer()
        create, = self.recorded()
        self.assertEqual(create[2], "Draft a project outline")
        self.assertEqual(create[create.index("--idempotency-key") + 1],
                         f"iphone-voice-capture:{source.stem}")


if __name__ == "__main__":
    unittest.main()
