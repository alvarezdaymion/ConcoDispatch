"""Offline-only audio transcription; optional faster-whisper loads on first use."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _get_model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError("Local audio transcription requires faster-whisper in the consumer's Python environment") from error
    try:
        # Provision this model separately. Queue processing must never download
        # weights or fall back to a network transcription service.
        return WhisperModel("base.en", device="cpu", compute_type="int8", local_files_only=True)
    except Exception as error:
        raise RuntimeError("Cannot load local base.en model; provision the offline model cache before retrying") from error


def transcribe_audio(path: Path) -> str:
    segments, _ = _get_model().transcribe(str(path), language="en", vad_filter=True)
    transcript = "\n".join(text for segment in segments if (text := segment.text.strip()))
    if not transcript:
        raise RuntimeError("Local audio transcript is empty")
    return transcript
