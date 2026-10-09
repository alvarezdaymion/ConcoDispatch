"""Isolated receiver tests: synthetic audio and mocked STT/Hermes, not device proof."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from voice_kanban import consumer

ROOT = Path(__file__).resolve().parents[1]


class AudioConsumerTests(unittest.TestCase):
    def test_bad_saved_routing_does_not_block_healthy_capture(self):
        self.run_consumer(expected=1, hermes=lambda args: (_ for _ in ()).throw(consumer.CaptureError('lost response')))
        for index, encoded in enumerate(('[]', '{}', '{"board":1,"profile":"","assignee":"default"}')):
            with self.subTest(encoded=encoded):
                with sqlite3.connect(self.db_path) as db:
                    db.execute('UPDATE captures SET routing_json = ? WHERE capture_id = ?', (encoded, self.capture_id))
                healthy = self.queue / f'capture-healthy-routing-{index:04d}.m4a'
                healthy.write_bytes(self.payload)
                self.run_consumer(expected=1, transcriber=lambda path: self.transcript)
                self.assertTrue(self.source.exists())
                self.assertFalse(healthy.exists())

    def test_optional_sends_follow_all_capture_delivery(self):
        second = self.queue / 'capture-second-audio-0002.m4a'
        second.write_bytes(self.payload)
        def send(*args, **kwargs):
            self.assertFalse(self.source.exists())
            self.assertFalse(second.exists())
            raise consumer.CaptureError('synthetic message timeout')
        with patch.object(consumer, 'NOTIFY_TARGET', 'synthetic-target'), patch.object(consumer, 'notify', side_effect=send) as notify:
            self.run_consumer(expected=1, transcriber=lambda path: self.transcript)
        self.assertEqual(notify.call_count, 2)
        self.assertEqual(self.receipt('COUNT(*)'), (2,))

    def test_retry_pins_board_profile_and_assignee_from_original_capture(self):
        attempts = []
        def first(args):
            attempts.append(args)
            raise consumer.CaptureError('synthetic lost response')
        with patch.object(consumer, 'BOARD', 'synthetic-board'), patch.object(consumer, 'PROFILE', 'synthetic-profile'), \
                patch.object(consumer, 'ASSIGNEE', 'synthetic-worker'):
            self.run_consumer(expected=1, hermes=first)
        def retry(args):
            attempts.append(args)
            self.assertEqual(args[:6], ['synthetic-hermes', '--profile', 'synthetic-profile', 'kanban', '--board', 'synthetic-board'])
            if 'create' in args:
                self.assertEqual(args[args.index('--assignee') + 1], 'synthetic-worker')
                return {'id': 't_synthetic_route'}
            return {'task': {'id': 't_synthetic_route', 'body': self.transcript}}
        with patch.object(consumer, 'BOARD', 'changed-board'), patch.object(consumer, 'PROFILE', 'changed-profile'), \
                patch.object(consumer, 'ASSIGNEE', 'changed-worker'):
            self.run_consumer(hermes=retry)
        self.assertEqual(attempts[0], attempts[1])
        self.assertFalse(self.source.exists())

    def setUp(self):
        scratch = ROOT / ".local"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.queue = self.root / "queue"
        self.queue.mkdir()
        self.state = self.root / "state"
        self.archive = self.state / "archive"
        self.db_path = self.state / "receipts.sqlite3"
        for name, value in dict(QUEUE_DIR=self.queue, STATE_DIR=self.state,
                                ARCHIVE_DIR=self.archive, DATABASE_PATH=self.db_path,
                                NOTIFY_TARGET="", HERMES="synthetic-hermes",
                                BOARD='', PROFILE='', ASSIGNEE='default').items():
            patcher = patch.object(consumer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.capture_id = "capture-synthetic-audio-0001"
        self.source = self.queue / (self.capture_id + ".m4a")
        self.payload = b"synthetic audio bytes\x00\xff"
        self.source.write_bytes(self.payload)
        self.transcript = "Opening amber telescope\n" + "A complete synthetic detail. " * 12000 + "Closing violet lighthouse"
        self.calls = []
        self.task = {}
        self.stt_calls = []

    def receipt(self, columns="status, attempts, last_error"):
        with sqlite3.connect(self.db_path) as db:
            return db.execute("SELECT " + columns + " FROM captures").fetchone()

    def transcribe(self, path):
        self.stt_calls.append(path)
        self.assertEqual(path, self.archive / (self.capture_id + ".m4a"))
        self.assertEqual(path.read_bytes(), self.payload)
        self.assertEqual(self.receipt("status"), ("archived",))
        return self.transcript

    def rebuild_historical_schema(self, *, with_transcript_digest=False):
        with sqlite3.connect(self.db_path) as db:
            db.execute("ALTER TABLE captures RENAME TO current_captures")
            db.execute("""CREATE TABLE captures (
                capture_id TEXT PRIMARY KEY, source_name TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL, archived_path TEXT NOT NULL,
                captured_at TEXT, status TEXT NOT NULL, task_id TEXT,
                attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL, notified_at REAL)""")
            if with_transcript_digest:
                db.execute("ALTER TABLE captures ADD COLUMN transcript_sha256 TEXT")
            columns = ', '.join(row[1] for row in db.execute("PRAGMA table_info(captures)"))
            db.execute(f"INSERT INTO captures SELECT {columns} FROM current_captures")
            db.execute("DROP TABLE current_captures")

    def hermes(self, args):
        self.calls.append(args)
        if args[1:3] == ["kanban", "create"]:
            body = Path(args[args.index("--body-file") + 1]).read_text()
            self.task = {"id": "t_synthetic_audio", "body": body}
            return {"id": self.task["id"]}
        self.assertEqual(args, ["synthetic-hermes", "kanban", "show", self.task["id"], "--json"])
        return {"task": self.task.copy()}

    def run_consumer(self, expected=0, transcriber=None, hermes=None):
        stderr = io.StringIO()
        with patch.object(consumer, "run_json", side_effect=hermes or self.hermes), redirect_stdout(io.StringIO()), redirect_stderr(stderr):
            result = consumer.main(transcriber=transcriber or self.transcribe)
        self.assertEqual(result, expected, stderr.getvalue())
        return stderr.getvalue()

    def test_audio_archived_before_transcription_full_body_readback(self):
        self.run_consumer()
        self.assertFalse(self.source.exists())
        self.assertEqual((self.archive / self.source.name).read_bytes(), self.payload)
        self.assertEqual(self.task["body"], self.transcript)
        self.assertTrue(self.task["body"].endswith("Closing violet lighthouse"))
        self.assertEqual(self.calls[0][3], "Opening amber telescope")
        self.assertEqual(self.calls[0][self.calls[0].index("--assignee") + 1], "default")
        self.assertEqual(self.calls[0][self.calls[0].index("--created-by") + 1], "iphone-voice-capture")
        self.assertEqual(self.calls[0][self.calls[0].index("--idempotency-key") + 1], "iphone-voice-capture:" + self.capture_id)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.receipt(), ("confirmed", 1, None))

    def test_failed_or_blank_transcription_retains_audio_and_receipt(self):
        for failure in (RuntimeError("synthetic unavailable model"), "  \n "):
            with self.subTest(failure=str(failure)):
                def failed(path):
                    self.transcribe(path)
                    if isinstance(failure, Exception):
                        raise failure
                    return failure
                self.run_consumer(expected=1, transcriber=failed)
                self.assertTrue(self.source.exists())
                self.assertEqual((self.archive / self.source.name).read_bytes(), self.payload)
                self.assertFalse(self.calls)
                self.assertEqual(self.receipt()[0], "archived")
                self.assertTrue(self.receipt()[2])
        self.assertEqual(self.receipt()[1], 2)

    def test_cached_transcript_survives_failed_create_restart_and_missing_source(self):
        def failing_create(args):
            self.hermes(args)
            raise consumer.CaptureError("synthetic lost response")
        self.run_consumer(expected=1, hermes=failing_create)
        self.source.unlink()
        self.run_consumer(transcriber=lambda path: self.fail("must reuse durable transcript"))
        self.assertEqual(len(self.stt_calls), 1)
        self.assertEqual(self.receipt(), ("confirmed", 2, None))
        self.assertEqual(self.task["body"], self.transcript)
        self.assertTrue((self.archive / self.source.name).exists())
        creates = [args for args in self.calls if args[2] == "create"]
        self.assertEqual(creates[0], creates[1])

    def test_text_archive_cannot_impersonate_audio_transcript(self):
        self.source.unlink()
        text_id = self.capture_id + ".m4a.transcript"
        text_source = self.queue / (text_id + ".txt")
        text_source.write_text(f"VOICEKANBAN/2\ncapture_id: {text_id}\n---\nUnrelated text task\n")
        self.run_consumer(hermes=lambda args: {"id": "t_synthetic_text"})
        self.source.write_bytes(self.payload)
        self.run_consumer(transcriber=lambda path: self.stt_calls.append(path) or self.transcript)
        self.assertEqual(len(self.stt_calls), 1, "text archive was reused as audio STT output")
        self.assertEqual(self.task["body"], self.transcript)

    def test_rejected_text_archive_cannot_seed_fresh_audio_transcript(self):
        self.source.unlink()
        text_id = self.capture_id + ".m4a.transcript"
        text_source = self.queue / "mismatched-capture.txt"
        text_source.write_text(f"VOICEKANBAN/2\ncapture_id: {text_id}\n---\nUnrelated text task\n")
        error = self.run_consumer(expected=1)
        self.assertIn("does not match payload", error)
        legacy = self.archive / (text_id + ".txt")
        self.assertEqual(legacy.read_bytes(), text_source.read_bytes())
        self.assertEqual(self.receipt("COUNT(*)"), (0,))
        self.assertFalse(self.calls)
        text_source.unlink()
        self.source.write_bytes(self.payload)

        self.run_consumer()
        self.assertEqual(len(self.stt_calls), 1, "unreceipted raw archive bypassed STT")
        self.assertEqual(self.task["body"], self.transcript)
        self.assertTrue(legacy.exists(), "raw archive must be preserved")

    def test_new_receipt_retry_ignores_flat_sidecar_after_failed_stt(self):
        self.run_consumer(expected=1, transcriber=lambda path: "")
        legacy = self.archive / (self.source.name + ".transcript.txt")
        legacy.write_text("Unrelated injected instruction")
        self.source.unlink()  # Restart through archived-audio recovery.

        self.run_consumer()
        self.assertEqual(len(self.stt_calls), 1, "new receipt retry consumed a legacy-looking archive")
        self.assertEqual(self.task["body"], self.transcript)
        self.assertEqual(self.receipt(), ("confirmed", 2, None))

    def test_modified_cached_transcript_is_not_dispatched(self):
        self.run_consumer(expected=1, hermes=lambda args: (_ for _ in ()).throw(consumer.CaptureError("lost response")))
        cached = self.archive / ".transcripts" / (self.source.name + ".transcript.txt")
        cached.write_text("Different unverified instruction")
        self.calls.clear()
        error = self.run_consumer(expected=1, transcriber=lambda path: self.fail("must not replace cached transcript"))
        self.assertFalse(self.calls)
        self.assertIn("transcript", error.lower())
        self.assertTrue(self.source.exists())

    def test_digest_schema_upgrade_does_not_grant_legacy_eligibility(self):
        self.run_consumer(expected=1, transcriber=lambda path: "")
        self.rebuild_historical_schema(with_transcript_digest=True)
        legacy = self.archive / (self.source.name + ".transcript.txt")
        legacy.write_text("Unrelated injected instruction")
        for _ in range(2):
            consumer.connect_database().close()
            self.assertEqual(self.receipt("transcript_sha256, legacy_transcript_eligible"), (None, 0))

        self.run_consumer()
        self.assertEqual(len(self.stt_calls), 1)
        self.assertEqual(self.task["body"], self.transcript)

    def test_legacy_receipt_and_sidecar_migrate_without_retranscribing(self):
        self.run_consumer(expected=1, hermes=lambda args: (_ for _ in ()).throw(consumer.CaptureError("lost response")))
        cached = self.archive / ".transcripts" / (self.source.name + ".transcript.txt")
        legacy = self.archive / cached.name
        cached.rename(legacy)
        self.rebuild_historical_schema()
        receipt_before = self.receipt()
        for _ in range(2):
            consumer.connect_database().close()
            self.assertEqual(self.receipt("transcript_sha256, legacy_transcript_eligible"), (None, 1))
            self.assertEqual(self.receipt(), receipt_before)

        def no_stt(path):
            self.fail("must preserve legacy STT output")
        def uncertain_create(args):
            self.hermes(args)
            raise consumer.CaptureError("synthetic lost response after migration")
        self.run_consumer(expected=1, transcriber=no_stt, hermes=uncertain_create)
        self.assertEqual(self.receipt("legacy_transcript_eligible"), (0,))
        self.source.unlink()
        self.run_consumer(transcriber=no_stt)
        self.assertEqual(self.task["body"], self.transcript)
        self.assertEqual(cached.read_text(), self.transcript)
        self.assertTrue(legacy.exists())
        self.assertTrue(self.receipt("transcript_sha256")[0])
        creates = [args for args in self.calls if args[2] == "create"]
        self.assertEqual(len(creates), 2)
        self.assertEqual(creates[0], creates[1])

    def test_missing_pinned_transcript_is_not_retranscribed(self):
        self.run_consumer(expected=1, hermes=lambda args: (_ for _ in ()).throw(consumer.CaptureError("lost response")))
        cached = self.archive / ".transcripts" / (self.source.name + ".transcript.txt")
        cached.unlink()
        # Even identical bytes in the flat namespace cannot repair a new receipt.
        (self.archive / cached.name).write_text(self.transcript)
        self.calls.clear()
        self.run_consumer(expected=1, transcriber=lambda path: self.fail("must restore original transcript"))
        self.assertFalse(self.calls)
        self.assertFalse(cached.exists())
        self.assertTrue(self.source.exists())

    def test_corrupt_legacy_orphan_does_not_block_healthy_queue(self):
        self.run_consumer()
        cached = self.archive / ".transcripts" / (self.source.name + ".transcript.txt")
        cached.write_bytes(b"\xff")
        with sqlite3.connect(self.db_path) as db:
            db.execute("UPDATE captures SET transcript_sha256 = NULL")
        healthy = self.queue / "capture-synthetic-healthy.txt"
        healthy.write_text("VOICEKANBAN/2\ncapture_id: capture-synthetic-healthy\n---\nHealthy task\n")
        self.calls.clear()
        def create(args):
            self.calls.append(args)
            return {"id": "t_synthetic_healthy"}
        with patch.object(consumer, "NOTIFY_TARGET", "synthetic-target"), patch.object(consumer, "notify") as notify:
            self.run_consumer(expected=1, hermes=create)
        self.assertFalse(healthy.exists())
        self.assertEqual(self.calls[0][3], "Healthy task")
        self.assertEqual(notify.call_count, 1)
        self.assertTrue(self.receipt("last_error")[0])

    def test_duplicate_extensions_and_numbered_suffix_replays_create_once(self):
        self.source.unlink()
        for suffix in (".m4a.m4a", ".m4a", ".m4a 2.m4a", " 2.m4a", " (2).m4a"):
            duplicate = self.queue / (self.capture_id + suffix)
            duplicate.write_bytes(self.payload)
            self.run_consumer()
            self.assertFalse(duplicate.exists())
        self.assertEqual(len(self.stt_calls), 1)
        self.assertEqual(sum(args[2] == "create" for args in self.calls), 1)
        self.assertEqual(self.receipt("COUNT(*)"), (1,))

    def test_all_audio_suffixes_and_long_first_line(self):
        self.source.unlink()
        self.transcript = "A" * 200 + "\nFinal phrase"
        for suffix in (".m4a", ".wav", ".mp3", ".caf", ".aiff"):
            with self.subTest(suffix=suffix):
                path = self.queue / ("capture-format-" + suffix[1:] + suffix)
                path.write_bytes(self.payload)
                self.run_consumer(transcriber=lambda archived: self.transcript)
                self.assertFalse(path.exists())
                self.assertTrue((self.archive / path.name).exists())
                self.assertEqual(self.calls[-2][3], "A" * 120)
                self.assertEqual(self.task["body"], self.transcript)

    def test_modified_source_is_not_deleted(self):
        def modifying(args):
            result = self.hermes(args)
            self.source.write_bytes(b"replacement recording")
            return result
        self.run_consumer(expected=1, hermes=modifying)
        self.assertEqual(self.source.read_bytes(), b"replacement recording")
        self.assertEqual((self.archive / self.source.name).read_bytes(), self.payload)
        self.assertTrue(self.receipt()[2])

    def test_replacement_after_cleanup_read_survives(self):
        original_read = consumer.read_stable
        queue_reads = []
        def replace_after_read(path):
            payload = original_read(path)
            if self.queue in path.parents:
                queue_reads.append(path)
                if len(queue_reads) == 2:
                    replacement = self.queue / "replacement.tmp"
                    replacement.write_bytes(b"new unarchived recording")
                    replacement.replace(self.source)
            return payload
        with patch.object(consumer, "read_stable", side_effect=replace_after_read):
            self.run_consumer()
        self.assertTrue(self.source.exists(), "cleanup deleted a replacement source")
        self.assertEqual(self.source.read_bytes(), b"new unarchived recording")
        self.assertEqual((self.archive / self.source.name).read_bytes(), self.payload)

    def test_native_readback_body_or_id_mismatch_retains_source(self):
        for field, value in (("body", "truncated body"), ("id", "t_wrong")):
            with self.subTest(field=field):
                def mismatch(args):
                    response = self.hermes(args)
                    if args[2] == "show":
                        response["task"][field] = value
                    return response
                self.run_consumer(expected=1, hermes=mismatch)
                self.assertTrue(self.source.exists())
                self.assertEqual(self.receipt()[0], "archived")
                self.assertIn("readback", self.receipt()[2])
        self.assertEqual(len(self.stt_calls), 1)
        self.run_consumer(transcriber=lambda path: self.fail("transcript already durable"))

    def test_pending_audio_recovers_from_archive_after_failed_stt(self):
        self.run_consumer(expected=1, transcriber=lambda path: "")
        self.source.unlink()
        self.run_consumer()
        self.assertEqual(self.receipt(), ("confirmed", 2, None))
        self.assertTrue((self.archive / self.source.name).exists())

    def test_symlink_audio_is_rejected(self):
        target = self.root / "original.m4a"
        self.source.rename(target)
        self.source.symlink_to(target)
        self.run_consumer(expected=1)
        self.assertTrue(self.source.is_symlink())
        self.assertEqual(target.read_bytes(), self.payload)
        self.assertFalse(self.stt_calls)
        self.assertFalse(self.calls)

    def test_unsafe_audio_filename_is_rejected(self):
        self.source.rename(self.queue / "short.m4a")
        self.run_consumer(expected=1)
        self.assertFalse(self.stt_calls)
        self.assertFalse(self.calls)

    def test_state_cannot_overlap_queue_or_use_symlink(self):
        for state in (self.queue, self.queue / "state"):
            with self.subTest(state=state), patch.object(consumer, "STATE_DIR", state):
                self.run_consumer(expected=1)
        target = self.root / "other-state"
        target.mkdir()
        self.state.symlink_to(target, target_is_directory=True)
        self.run_consumer(expected=1)
        self.assertEqual(list(target.iterdir()), [])
        self.assertTrue(self.source.exists())

    def test_concurrent_consumer_exits_without_transcription(self):
        import fcntl
        self.state.mkdir()
        with (self.state / "consumer.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.run_consumer()
        self.assertFalse(self.calls)
        self.assertFalse(self.stt_calls)
        self.assertTrue(self.source.exists())


    def test_raw_and_transcript_fsync_precede_their_consumers(self):
        fsynced = []
        real_fsync = os.fsync
        def track(fd):
            real_fsync(fd)
            for temporary in self.archive.rglob(".*.tmp"):
                if temporary.stat().st_ino == os.fstat(fd).st_ino:
                    fsynced.append(temporary.read_bytes())
        def transcribe(path):
            self.assertIn(self.payload, fsynced)
            return self.transcribe(path)
        def create(args):
            self.assertIn(self.transcript.encode(), fsynced)
            return self.hermes(args)
        with patch.object(consumer.os, "fsync", side_effect=track):
            self.run_consumer(transcriber=transcribe, hermes=create)

    def test_modified_archive_cannot_be_recovered_as_original(self):
        self.run_consumer(expected=1, transcriber=lambda path: "")
        self.source.unlink()
        (self.archive / self.source.name).write_bytes(b"corrupt archive")
        self.run_consumer(expected=1)
        self.assertFalse(self.calls)
        self.assertFalse(self.stt_calls)

    def test_symlink_replacement_after_task_readback_is_not_unlinked(self):
        target = self.root / "keep.m4a"
        target.write_bytes(self.payload)
        def replace(args):
            result = self.hermes(args)
            if args[2] == "show":
                self.source.unlink()
                self.source.symlink_to(target)
            return result
        self.run_consumer(expected=1, hermes=replace)
        self.assertTrue(self.source.is_symlink())
        self.assertEqual(target.read_bytes(), self.payload)

    def test_reappearing_changed_source_during_archive_recovery_is_retained(self):
        self.run_consumer(expected=1, transcriber=lambda path: "")
        self.source.unlink()
        def reappear(path):
            self.source.write_bytes(b"new recording")
            return self.transcribe(path)
        self.run_consumer(expected=1, transcriber=reappear)
        self.assertEqual(self.source.read_bytes(), b"new recording")
        self.assertEqual((self.archive / self.source.name).read_bytes(), self.payload)

    def test_fresh_process_recovers_transcript_without_retranscribing(self):
        # Both subprocesses use explicit fakes; no installed Whisper or Hermes.
        env = {key: value for key, value in os.environ.items() if not key.startswith("VOICE_KANBAN_")}
        env.update(VOICE_KANBAN_QUEUE_DIR=str(self.queue), VOICE_KANBAN_STATE_DIR=str(self.state),
                   VOICE_KANBAN_NOTIFY_TARGET="", VOICE_KANBAN_HERMES_BIN="synthetic-hermes")
        first = """
from voice_kanban import consumer
def create(args):
    raise consumer.CaptureError('synthetic lost create response')
consumer.run_json = create
raise SystemExit(consumer.main(transcriber=lambda path: 'Persist this whole transcript'))
"""
        second = """
from pathlib import Path
from voice_kanban import consumer
def transcribe(path):
    raise AssertionError('must not transcribe after restart')
def run(args):
    if args[2] == 'create':
        assert Path(args[args.index('--body-file') + 1]).read_text() == 'Persist this whole transcript'
        return {'id': 't_synthetic_audio'}
    return {'task': {'id': 't_synthetic_audio', 'body': 'Persist this whole transcript'}}
consumer.run_json = run
raise SystemExit(consumer.main(transcriber=transcribe))
"""
        result = subprocess.run([sys.executable, "-c", first], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.source.unlink()
        result = subprocess.run([sys.executable, "-c", second], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.receipt(), ("confirmed", 2, None))


    def test_default_transcriber_imports_from_script_and_module_entrypoints(self):
        # Fake only the optional library. Both real CLI entrypoints must lazily
        # import transcribe.py, then retain their durable transcript on CLI error.
        (self.root / "faster_whisper.py").write_text(
            "from types import SimpleNamespace\n"
            "class WhisperModel:\n"
            "    def __init__(self, name, **kwargs):\n"
            "        assert name == 'base.en' and kwargs['local_files_only'] is True\n"
            "    def transcribe(self, path, **kwargs):\n"
            "        assert kwargs == {'language': 'en', 'vad_filter': True}\n"
            "        return iter([SimpleNamespace(text='Synthetic local import proof')]), None\n"
        )
        self.source.unlink()
        env = {key: value for key, value in os.environ.items() if not key.startswith("VOICE_KANBAN_")}
        env.update(VOICE_KANBAN_QUEUE_DIR=str(self.queue), VOICE_KANBAN_STATE_DIR=str(self.state),
                   VOICE_KANBAN_NOTIFY_TARGET="", VOICE_KANBAN_HERMES_BIN=str(self.root / "missing-hermes"),
                   PYTHONPATH=os.pathsep.join((str(self.root), str(ROOT))))
        entries = ([str(ROOT / "voice_kanban" / "consumer.py")], ["-m", "voice_kanban.consumer"])
        for index, entry in enumerate(entries):
            with self.subTest(entry=entry):
                name = f"capture-script-import-{index:04d}.m4a"
                source = self.queue / name
                source.write_bytes(self.payload)
                result = subprocess.run([sys.executable] + entry, cwd=ROOT, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("missing-hermes", result.stderr)
                transcript = self.archive / ".transcripts" / (name + ".transcript.txt")
                self.assertEqual(transcript.read_text(), "Synthetic local import proof")
                self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
