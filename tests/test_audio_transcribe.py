"""Offline STT contract tests with a fake faster-whisper module; no downloads."""
from __future__ import annotations

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class LocalTranscriptionTests(unittest.TestCase):
    def setUp(self):
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
                text = self.module.transcribe_audio(Path("synthetic-audio.m4a"))
                self.assertEqual(text, "Opening amber telescope\nClosing violet lighthouse")
        constructor.assert_called_once_with("base.en", device="cpu", compute_type="int8", local_files_only=True)
        model.transcribe.assert_called_with("synthetic-audio.m4a", language="en", vad_filter=True)

    def test_blank_transcript_is_an_error(self):
        model = Mock()
        model.transcribe.return_value = (iter([SimpleNamespace(text="  ")]), None)
        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=Mock(return_value=model))}):
            with self.assertRaisesRegex(RuntimeError, "empty"):
                self.module.transcribe_audio(Path("synthetic-silence.wav"))

    def test_uncached_model_failure_is_not_downloaded_or_fallbacked(self):
        constructor = Mock(side_effect=OSError("synthetic missing cache"))
        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=constructor)}):
            with self.assertRaisesRegex(RuntimeError, "local|offline|cache"):
                self.module.transcribe_audio(Path("synthetic-audio.caf"))
        constructor.assert_called_once_with("base.en", device="cpu", compute_type="int8", local_files_only=True)

    def test_module_import_does_not_require_optional_dependency(self):
        with patch.dict(sys.modules, {"faster_whisper": None}):
            importlib.reload(self.module)
            with self.assertRaisesRegex(RuntimeError, "faster-whisper"):
                self.module.transcribe_audio(Path("synthetic-audio.mp3"))


if __name__ == "__main__":
    unittest.main()
