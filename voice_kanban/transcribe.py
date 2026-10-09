"""Bounded, local Apple audio transcription using explicitly prepared assets."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess


def transcribe_audio(path: Path) -> str:
    backend = os.environ.get('VOICE_KANBAN_STT_BACKEND', 'apple')
    timeout = float(os.environ.get('VOICE_KANBAN_STT_TIMEOUT', '600'))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('STT timeout must be positive and finite')
    if backend != 'apple':
        raise RuntimeError('Only Apple transcription is supported; no fallback is available')
    helper = os.environ.get('VOICE_KANBAN_NATIVE_BIN')
    if not helper:
        raise RuntimeError('Set VOICE_KANBAN_NATIVE_BIN to the compiled native speech helper')
    arguments = [helper, '--locale', os.environ.get('VOICE_KANBAN_LOCALE', 'en-US'), str(path)]
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
