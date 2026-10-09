"""Offline STT contract tests with a fake faster-whisper module; no downloads."""
from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class LocalTranscriptionTests(unittest.TestCase):
    def test_deadline_and_invalid_output_fail_without_fallback(self):
        env = {'VOICE_KANBAN_STT_BACKEND': 'apple', 'VOICE_KANBAN_NATIVE_BIN': '/synthetic/transcribe'}
        for response in ('{}', '[]', '{"text":" "}', 'not-json'):
            with self.subTest(response=response), patch.dict(os.environ, env), \
                    patch.object(self.module.subprocess, 'run', return_value=SimpleNamespace(stdout=response)) as run:
                with self.assertRaises((RuntimeError, ValueError)):
                    self.module.transcribe_audio(Path('synthetic.wav'))
                self.assertEqual(run.call_count, 1)
        with patch.dict(os.environ, env), patch.object(self.module.subprocess, 'run', side_effect=subprocess.TimeoutExpired('helper', 1)):
            with self.assertRaisesRegex(RuntimeError, 'exceeded'):
                self.module.transcribe_audio(Path('synthetic.wav'))
        for value in ('0', '-1', 'nan', 'inf'):
            with self.subTest(timeout=value), patch.dict(os.environ, dict(env, VOICE_KANBAN_STT_TIMEOUT=value)), \
                    patch.object(self.module.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    self.module.transcribe_audio(Path('synthetic.wav'))
                run.assert_not_called()

    def test_whisper_backend_runs_in_a_bounded_worker(self):
        with patch.dict(os.environ, {'VOICE_KANBAN_STT_BACKEND': 'whisper'}), \
                patch.object(self.module.subprocess, 'run', return_value=SimpleNamespace(stdout='{"text":"Synthetic full text"}')) as run:
            self.assertEqual(self.module.transcribe_audio(Path('synthetic.wav')), 'Synthetic full text')
        self.assertEqual(run.call_args.args[0][0], sys.executable)
        self.assertEqual(run.call_args.kwargs['timeout'], 600)
        self.assertEqual(run.call_args.args[0][-1], 'synthetic.wav')

    def test_apple_backend_uses_local_helper_with_deadline(self):
        response = SimpleNamespace(stdout='{"text": "Opening amber telescope\\nClosing violet lighthouse"}')
        with patch.dict(os.environ, {'VOICE_KANBAN_STT_BACKEND': 'apple',
                                    'VOICE_KANBAN_NATIVE_BIN': '/synthetic/transcribe',
                                    'VOICE_KANBAN_STT_TIMEOUT': '12'}), \
                patch.object(self.module.subprocess, 'run', return_value=response) as run:
            text = self.module.transcribe_audio(Path('synthetic-audio.m4a'))
        self.assertTrue(text.endswith('Closing violet lighthouse'))
        self.assertEqual(run.call_args.kwargs['timeout'], 12)
        self.assertEqual(run.call_args.args[0], ['/synthetic/transcribe', '--locale', 'en-US', 'synthetic-audio.m4a'])
        self.assertNotIn('--prepare', run.call_args.args[0])

    def setUp(self):
        environment = patch.dict(os.environ, {'VOICE_KANBAN_STT_TIMEOUT': '600', 'VOICE_KANBAN_LOCALE': 'en-US'})
        environment.start()
        self.addCleanup(environment.stop)
        self.module = importlib.import_module("voice_kanban.transcribe")
        self.module._get_model.cache_clear()
        self.addCleanup(self.module._get_model.cache_clear)

    def test_model_is_local_cpu_int8_cached_and_segments_consumed_fully(self):
        model = Mock()
        def segments(*args, **kwargs):
            return iter([SimpleNamespace(text=" Opening amber telescope "),
                         SimpleNamespace(text=" "),
                         SimpleNamespace(text="Closing violet lighthouse")]), None
        model.transcribe.side_effect = segments
        constructor = Mock(return_value=model)
        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=constructor)}):
            for _ in range(2):
                text = self.module.transcribe_whisper(Path("synthetic-audio.m4a"))
                self.assertEqual(text, "Opening amber telescope\nClosing violet lighthouse")
        constructor.assert_called_once_with("base.en", device="cpu", compute_type="int8", local_files_only=True)
        model.transcribe.assert_called_with("synthetic-audio.m4a", language="en", vad_filter=True)

    def test_blank_transcript_is_an_error(self):
        model = Mock()
        model.transcribe.return_value = (iter([SimpleNamespace(text="  ")]), None)
        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=Mock(return_value=model))}):
            with self.assertRaisesRegex(RuntimeError, "empty"):
                self.module.transcribe_whisper(Path("synthetic-silence.wav"))

    def test_uncached_model_failure_is_not_downloaded_or_fallbacked(self):
        constructor = Mock(side_effect=OSError("synthetic missing cache"))
        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=constructor)}):
            with self.assertRaisesRegex(RuntimeError, "local|offline|cache"):
                self.module.transcribe_whisper(Path("synthetic-audio.caf"))
        constructor.assert_called_once_with("base.en", device="cpu", compute_type="int8", local_files_only=True)

    def test_module_import_does_not_require_optional_dependency(self):
        with patch.dict(sys.modules, {"faster_whisper": None}):
            importlib.reload(self.module)
            with self.assertRaisesRegex(RuntimeError, "faster-whisper"):
                self.module.transcribe_whisper(Path("synthetic-audio.mp3"))


if __name__ == "__main__":
    unittest.main()
