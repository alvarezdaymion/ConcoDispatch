"""Offline-only audio transcription; optional faster-whisper loads on first use."""
from __future__ import annotations

from functools import lru_cache
import json
import math
import os
from pathlib import Path
import subprocess
import sys


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
    backend = os.environ.get('VOICE_KANBAN_STT_BACKEND', 'whisper')
    timeout = float(os.environ.get('VOICE_KANBAN_STT_TIMEOUT', '600'))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('STT timeout must be positive and finite')
    if backend == 'apple':
        helper = os.environ.get('VOICE_KANBAN_NATIVE_BIN')
        if not helper:
            raise RuntimeError('Set VOICE_KANBAN_NATIVE_BIN to the compiled native speech helper')
        arguments = [helper, '--locale', os.environ.get('VOICE_KANBAN_LOCALE', 'en-US'), str(path)]
    elif backend == 'whisper':
        arguments = [sys.executable, str(Path(__file__).resolve()), str(path)]
    else:
        raise RuntimeError('STT backend must be apple or whisper; no cloud fallback is supported')
    try:
        result = subprocess.run(arguments, text=True, capture_output=True, check=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f'Local transcription exceeded {timeout:g} seconds') from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f'Local transcription failed: {(error.stderr or str(error))[-1024:]}') from error
    payload = json.loads(result.stdout)
    text = payload.get('text') if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError('Local audio transcript is empty')
    return text


def transcribe_whisper(path: Path) -> str:
    """Worker-only local Whisper implementation; parent owns the deadline."""
    segments, _ = _get_model().transcribe(str(path), language="en", vad_filter=True)
    transcript = "\n".join(text for segment in segments if (text := segment.text.strip()))
    if not transcript:
        raise RuntimeError("Local audio transcript is empty")
    return transcript


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: transcribe.py AUDIO_FILE')
    print(json.dumps({'text': transcribe_whisper(Path(sys.argv[1]))}))
