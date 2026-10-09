#!/usr/bin/env python3
"""Opt-in synthetic audio → real local Hermes board → replay, without a gateway."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run(arguments, env, timeout=60):
    result = subprocess.run(arguments, env=env, cwd=ROOT, capture_output=True, text=True,
                            check=True, timeout=timeout)
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path, required=True, help='Synthetic narration only; never use private recordings')
    parser.add_argument('--native-bin', type=Path, required=True)
    parser.add_argument('--hermes-bin', type=Path, required=True)
    parser.add_argument('--expect', action='append', required=True, help='Required phrase; repeat for opening/ending/context')
    parser.add_argument('--output', type=Path, default=ROOT / '.local/audio-integration-proof.json')
    args = parser.parse_args()
    audio, native, hermes = (p.expanduser().resolve(strict=True) for p in (args.audio, args.native_bin, args.hermes_bin))
    scratch = ROOT / '.local'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='audio-integration-', dir=scratch) as temporary:
        fixture = Path(temporary)
        home, queue, state = fixture / 'home', fixture / 'queue', fixture / 'state'
        queue.mkdir()
        home.mkdir()
        kanban_home = fixture / 'kanban-home'
        db = kanban_home / 'kanban.db'
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('HERMES_', 'VOICE_KANBAN_'))}
        env.update(HOME=str(home), HERMES_HOME=str(home / '.hermes'), HERMES_KANBAN_HOME=str(kanban_home), HERMES_KANBAN_DB=str(db),
                   HERMES_KANBAN_BOARD='default', VOICE_KANBAN_HERMES_BIN=str(hermes),
                   VOICE_KANBAN_QUEUE_DIR=str(queue), VOICE_KANBAN_STATE_DIR=str(state),
                   VOICE_KANBAN_STT_BACKEND='apple', VOICE_KANBAN_NATIVE_BIN=str(native),
                   VOICE_KANBAN_BOARD='default', VOICE_KANBAN_ASSIGNEE='default',
                   VOICE_KANBAN_NOTIFY_TARGET='', PYTHONDONTWRITEBYTECODE='1')
        # Explicit --board outranks HERMES_KANBAN_DB; pin the board root too.
        run([str(hermes), 'kanban', '--board', 'default', 'init'], env)
        if not db.is_file():
            raise RuntimeError('CLI did not initialize the isolated database; stop before creating work')
        source = queue / ('capture-integration-synthetic-0001' + audio.suffix.lower())
        shutil.copyfile(audio, source)
        digest = hashlib.sha256(audio.read_bytes()).hexdigest()
        start = time.monotonic()
        run([sys.executable, '-m', 'voice_kanban.consumer'], env, timeout=660)
        elapsed = time.monotonic() - start
        with sqlite3.connect(state / 'receipts.sqlite3') as receipts:
            task_id, status = receipts.execute('SELECT task_id, status FROM captures').fetchone()
        if status != 'confirmed' or source.exists():
            raise RuntimeError('Receiver did not confirm and clean the capture')
        shown = json.loads(run([str(hermes), 'kanban', '--board', 'default', 'show', task_id, '--json'], env))
        task = shown['task']
        transcript = (state / 'archive/.transcripts' / (source.name + '.transcript.txt')).read_text()
        if task['body'] != transcript:
            raise RuntimeError('Native board body differs from the durable transcript')
        if hashlib.sha256((state / 'archive' / source.name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Archived recording changed')
        normalized = ' '.join(re.findall(r'\w+', transcript.lower()))
        for phrase in args.expect:
            if ' '.join(re.findall(r'\w+', phrase.lower())) not in normalized:
                raise RuntimeError('Transcription omitted required synthetic phrase: ' + phrase)
        shutil.copyfile(audio, source)
        # Replay must use the pinned cache even when the recognizer disappears.
        env['VOICE_KANBAN_NATIVE_BIN'] = str(fixture / 'missing-native-helper')
        run([sys.executable, '-m', 'voice_kanban.consumer'], env)
        with sqlite3.connect(db) as board:
            count = board.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
        if count != 1 or source.exists():
            raise RuntimeError('Replay duplicated work or failed safe cleanup')
        report = {'passed': True, 'task_id': task_id, 'task_count_after_replay': count,
                  'receipt_status': status, 'audio_sha256': digest,
                  'full_body_readback': True, 'replay_without_recognizer': True,
                  'required_phrases': args.expect, 'elapsed_seconds': round(elapsed, 3),
                  'transcript': transcript, 'worker_started': False,
                  'limits': 'No gateway, live board, microphone, phone, iCloud or loaded LaunchAgent was exercised.'}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
