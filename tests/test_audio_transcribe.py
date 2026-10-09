"""Bounded Apple transcription contract; no native tools or downloads."""
import importlib
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class LocalTranscriptionTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {'VOICE_KANBAN_STT_BACKEND': 'apple',
                                             'VOICE_KANBAN_NATIVE_BIN': '/synthetic/transcribe',
                                             'VOICE_KANBAN_STT_TIMEOUT': '600',
                                             'VOICE_KANBAN_LOCALE': 'en-US'})
        environment.start()
        self.addCleanup(environment.stop)
        self.module = importlib.import_module('voice_kanban.transcribe')

    def test_removed_backends_are_rejected_before_any_process_runs(self):
        for backend in ('whisper', 'unknown'):
            with self.subTest(backend=backend), patch.dict(os.environ, {'VOICE_KANBAN_STT_BACKEND': backend}), \
                    patch.object(self.module.subprocess, 'run', return_value=SimpleNamespace(stdout='{"text":"Full text"}')) as run:
                with self.assertRaisesRegex(RuntimeError, 'Apple|apple'):
                    self.module.transcribe_audio(Path('synthetic.wav'))
                run.assert_not_called()

    def test_apple_is_the_default_backend(self):
        with patch.dict(os.environ, {'VOICE_KANBAN_NATIVE_BIN': '/synthetic/transcribe'}, clear=True), \
                patch.object(self.module.subprocess, 'run', return_value=SimpleNamespace(stdout='{"text":"Full text"}')) as run:
            self.assertEqual(self.module.transcribe_audio(Path('synthetic.wav')), 'Full text')
        self.assertEqual(run.call_args.args[0][0], '/synthetic/transcribe')
        self.assertEqual(run.call_args.kwargs['timeout'], 600)

    def test_deadline_and_invalid_output_fail_without_fallback(self):
        for response in ('{}', '[]', '{"text":" "}', 'not-json'):
            with self.subTest(response=response), \
                    patch.object(self.module.subprocess, 'run', return_value=SimpleNamespace(stdout=response)) as run:
                with self.assertRaises((RuntimeError, ValueError)):
                    self.module.transcribe_audio(Path('synthetic.wav'))
                self.assertEqual(run.call_count, 1)
        with patch.object(self.module.subprocess, 'run', side_effect=subprocess.TimeoutExpired('helper', 1)):
            with self.assertRaisesRegex(RuntimeError, 'exceeded'):
                self.module.transcribe_audio(Path('synthetic.wav'))
        for value in ('0', '-1', 'nan', 'inf'):
            with self.subTest(timeout=value), patch.dict(os.environ, {'VOICE_KANBAN_STT_TIMEOUT': value}), \
                    patch.object(self.module.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    self.module.transcribe_audio(Path('synthetic.wav'))
                run.assert_not_called()

    def test_apple_backend_uses_local_helper_with_deadline(self):
        response = SimpleNamespace(stdout='{"text": "Opening amber telescope\\nClosing violet lighthouse"}')
        with patch.dict(os.environ, {'VOICE_KANBAN_STT_TIMEOUT': '12'}), \
                patch.object(self.module.subprocess, 'run', return_value=response) as run:
            text = self.module.transcribe_audio(Path('synthetic-audio.m4a'))
        self.assertTrue(text.endswith('Closing violet lighthouse'))
        self.assertEqual(run.call_args.kwargs['timeout'], 12)
        self.assertEqual(run.call_args.args[0], ['/synthetic/transcribe', '--locale', 'en-US', 'synthetic-audio.m4a'])
        self.assertNotIn('--prepare', run.call_args.args[0])

    def test_missing_helper_setting_is_an_error(self):
        with patch.dict(os.environ, {'VOICE_KANBAN_NATIVE_BIN': ''}), \
                patch.object(self.module.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'NATIVE_BIN'):
                self.module.transcribe_audio(Path('synthetic.wav'))
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
