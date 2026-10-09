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
                                NOTIFY_TARGET="", HERMES="synthetic-hermes").items():
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
            for temporary in self.archive.glob(".*.tmp"):
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
                transcript = self.archive / (name + ".transcript.txt")
                self.assertEqual(transcript.read_text(), "Synthetic local import proof")
                self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
