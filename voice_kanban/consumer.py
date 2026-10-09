#!/usr/bin/env python3
"""Durably bridge queued audio and legacy dictation into Hermes Kanban."""
from __future__ import annotations

from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
from typing import Any, Callable

HERMES = os.environ.get(
    "VOICE_KANBAN_HERMES_BIN",
    shutil.which("hermes") or str(Path.home() / ".hermes/hermes-agent/venv/bin/hermes"),
)
QUEUE_DIR = Path(os.environ.get(
    "VOICE_KANBAN_QUEUE_DIR",
    str(Path.home() / "Library/Mobile Documents/"
        "iCloud~is~workflow~my~workflows/Documents/VoiceKanbanInbox"),
)).expanduser()
STATE_DIR = Path(os.environ.get(
    "VOICE_KANBAN_STATE_DIR",
    str(Path.home() / "Library/Application Support/Hermes Voice Kanban"),
)).expanduser()
ENVELOPE_MARKER = os.environ.get("VOICE_KANBAN_ENVELOPE_MARKER", "VOICEKANBAN/2")
NOTIFY_TARGET = os.environ.get("VOICE_KANBAN_NOTIFY_TARGET", "").strip()
DATABASE_PATH = STATE_DIR / "receipts.sqlite3"
ARCHIVE_DIR = STATE_DIR / "archive"
CAPTURE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._,-]{7,127}$")
AUDIO_SUFFIXES = {".m4a", ".wav", ".mp3", ".caf", ".aiff"}


class CaptureError(RuntimeError):
    """A capture cannot be processed safely."""


def run_json(arguments: list[str]) -> Any:
    completed = subprocess.run(arguments, text=True, capture_output=True, check=True)
    return json.loads(completed.stdout)


def queue_files() -> list[Path]:
    if not QUEUE_DIR.exists():
        return []
    if not QUEUE_DIR.is_dir():
        raise CaptureError(f"Voice queue is not a directory: {QUEUE_DIR}")
    return sorted(path for path in QUEUE_DIR.iterdir()
                  if (path.is_file() or path.is_symlink())
                  and path.suffix.lower() in AUDIO_SUFFIXES | {".txt"})


def read_stable(path: Path) -> bytes:
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise CaptureError(f"Capture is not a regular file: {path.name}")
        payload = handle.read()
        after = os.fstat(handle.fileno())
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if identity(before) != identity(after) or identity(after) != identity(path.lstat()):
        raise CaptureError(f"Capture changed while being read: {path.name}")
    return payload


def audio_capture_id(path: Path) -> str:
    # Shortcuts can append the extension twice; Files can add a numbered copy
    # suffix. Strip only these suffix forms, never arbitrary ID characters.
    name = path.name
    while True:
        previous = name
        name = re.sub(r" (?:\([0-9]+\)|[0-9]+)$", "", name)
        suffix = Path(name).suffix
        if suffix.lower() in AUDIO_SUFFIXES:
            name = name[:-len(suffix)]
        if name == previous:
            break
    if not CAPTURE_ID_PATTERN.fullmatch(name):
        raise CaptureError("Audio filename has an invalid capture_id")
    return name


def parse_envelope(payload: bytes, source_name: str) -> tuple[str, str, str | None]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CaptureError("Capture payload is not valid UTF-8") from error
    lines = text.splitlines()
    if not lines or lines[0] != ENVELOPE_MARKER:
        transcript = text.strip()
        if not transcript:
            raise CaptureError("Capture transcript is empty")
        legacy_digest = hashlib.sha256(source_name.encode("utf-8") + b"\0" + payload).hexdigest()
        return f"legacy-{legacy_digest}", transcript, None
    try:
        separator = lines.index("---")
    except ValueError as error:
        raise CaptureError("Capture envelope is missing its transcript separator") from error
    metadata: dict[str, str] = {}
    for line in lines[1:separator]:
        key, marker, value = line.partition(":")
        if not marker:
            raise CaptureError("Capture envelope contains malformed metadata")
        metadata[key.strip()] = value.strip()
    capture_id = metadata.get("capture_id", "")
    if not CAPTURE_ID_PATTERN.fullmatch(capture_id):
        raise CaptureError("Capture envelope has an invalid capture_id")
    transcript = "\n".join(lines[separator + 1:]).strip()
    if not transcript:
        raise CaptureError("Capture transcript is empty")
    return capture_id, transcript, metadata.get("captured_at")


def connect_database() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(DATABASE_PATH)
    database.execute("PRAGMA journal_mode=WAL")
    database.execute("PRAGMA synchronous=FULL")
    database.execute("""
        CREATE TABLE IF NOT EXISTS captures (
            capture_id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            archived_path TEXT NOT NULL,
            captured_at TEXT,
            status TEXT NOT NULL,
            task_id TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            notified_at REAL
        )
    """)
    return database


def archive_payload(capture_id: str, payload: bytes, suffix: str = ".txt") -> tuple[Path, str]:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    destination = ARCHIVE_DIR / f"{capture_id}{suffix}"
    digest = hashlib.sha256(payload).hexdigest()
    if destination.exists() or destination.is_symlink():
        if hashlib.sha256(read_stable(destination)).hexdigest() != digest:
            raise CaptureError(f"Archive collision for capture {capture_id}")
        return destination, digest
    write_durable(destination, payload)
    return destination, digest


def write_durable(destination: Path, payload: bytes) -> None:
    if destination.is_symlink():
        raise CaptureError(f"Refusing symlink state file: {destination.name}")
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def notify(capture_id: str, task_id: str, transcript: str) -> None:
    if not NOTIFY_TARGET:
        return
    summary = " ".join(transcript.split())
    if len(summary) > 120:
        summary = summary[:117] + "..."
    subprocess.run([
        HERMES, "send", "--to", NOTIFY_TARGET,
        f"Voice capture {capture_id[-6:]} confirmed in Kanban as {task_id}: {summary}",
    ], text=True, capture_output=True, check=True)


def process_capture(database: sqlite3.Connection, path: Path,
                    transcriber: Callable[[Path], str] | None = None,
                    *, source_path: Path | None = None) -> str:
    try:
        return _process_capture(database, path, transcriber, source_path=source_path)
    except (OSError, sqlite3.Error, subprocess.CalledProcessError,
            ValueError, CaptureError) as error:
        capture_id = None
        if path.suffix.lower() in AUDIO_SUFFIXES:
            try:
                capture_id = audio_capture_id(path)
            except CaptureError:
                pass
        database.execute("""
            UPDATE captures SET last_error = ?, updated_at = ?
            WHERE capture_id = ? OR source_name = ? OR archived_path = ?
        """, (str(error), time.time(), capture_id, path.name, str(path)))
        database.commit()
        raise


def _process_capture(database: sqlite3.Connection, path: Path,
                     transcriber: Callable[[Path], str] | None,
                     *, source_path: Path | None) -> str:
    payload = read_stable(path)
    audio = path.suffix.lower() in AUDIO_SUFFIXES
    if audio:
        capture_id, transcript, captured_at = audio_capture_id(path), "", None
    else:
        capture_id, transcript, captured_at = parse_envelope(payload, path.name)
    archive_path, digest = archive_payload(capture_id, payload, path.suffix.lower() if audio else ".txt")
    if not audio and payload.startswith((ENVELOPE_MARKER + "\n").encode("utf-8")) and path.stem != capture_id:
        raise CaptureError(f"Capture filename {path.stem!r} does not match payload {capture_id!r}")
    now = time.time()
    existing = database.execute(
        "SELECT payload_sha256, status, task_id, notified_at, archived_path FROM captures WHERE capture_id = ?",
        (capture_id,),
    ).fetchone()
    if existing and existing[0] != digest:
        raise CaptureError(f"Capture ID reused with different content: {capture_id}")
    if not existing:
        database.execute("""
            INSERT INTO captures (
                capture_id, source_name, payload_sha256, archived_path,
                captured_at, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'archived', ?, ?)
        """, (capture_id, path.name, digest, str(archive_path), captured_at, now, now))
        database.commit()
        status, task_id, notified_at = "archived", None, None
    else:
        _, status, task_id, notified_at, saved_archive = existing
        archive_path = Path(saved_archive)
        if archive_path.parent != ARCHIVE_DIR or hashlib.sha256(read_stable(archive_path)).hexdigest() != digest:
            raise CaptureError(f"Archived payload does not match receipt: {capture_id}")

    transcript_path = archive_path.with_name(archive_path.name + ".transcript.txt")
    if status != "confirmed":
        database.execute(
            "UPDATE captures SET attempts = attempts + 1, updated_at = ? WHERE capture_id = ?",
            (time.time(), capture_id),
        )
        database.commit()
    if audio:
        if transcript_path.exists() or transcript_path.is_symlink():
            transcript = read_stable(transcript_path).decode("utf-8")
        elif status != "confirmed":
            if transcriber is None:
                if __package__:
                    from .transcribe import transcribe_audio
                else:
                    from transcribe import transcribe_audio
                transcriber = transcribe_audio
            try:
                transcript = transcriber(archive_path)
            except Exception as error:
                raise CaptureError(f"Local audio transcription failed: {error}") from error
            if not isinstance(transcript, str) or not transcript.strip():
                raise CaptureError("Audio transcript is empty")
            write_durable(transcript_path, transcript.encode("utf-8"))
        if not transcript.strip():
            raise CaptureError("Durable audio transcript is missing or empty")

    if status != "confirmed":
        arguments = [
            HERMES, "kanban", "create", transcript.strip().splitlines()[0][:120] if audio else transcript,
            "--assignee", "default", "--created-by", "iphone-voice-capture",
            "--idempotency-key", f"iphone-voice-capture:{capture_id}",
        ]
        if audio:
            arguments.extend(["--body-file", str(transcript_path)])
        task = run_json(arguments + ["--json"])
        task_id = task.get("id") if isinstance(task, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise CaptureError("Hermes did not return a Kanban task ID")
        if audio:
            shown = run_json([HERMES, "kanban", "show", str(task_id), "--json"])
            actual = shown.get("task", {}) if isinstance(shown, dict) else {}
            if not isinstance(actual, dict) or actual.get("id") != task_id or actual.get("body") != transcript:
                raise CaptureError("Kanban readback did not match the full audio transcript")
        database.execute("""
            UPDATE captures
            SET status = 'confirmed', task_id = ?, last_error = NULL, updated_at = ?
            WHERE capture_id = ?
        """, (task_id, time.time(), capture_id))
        database.commit()
        notified_at = None

    if NOTIFY_TARGET and notified_at is None:
        notify(capture_id, str(task_id), transcript)
        database.execute(
            "UPDATE captures SET notified_at = ?, updated_at = ? WHERE capture_id = ?",
            (time.time(), time.time(), capture_id),
        )
        database.commit()

    path = source_path if source_path is not None else path
    if path.exists() or path.is_symlink():
        current_payload = read_stable(path)
        if hashlib.sha256(current_payload).hexdigest() != digest:
            raise CaptureError(f"Capture {capture_id} changed after local archival; source retained")
        path.unlink()
    return str(task_id)


def retry_orphaned_notifications(database: sqlite3.Connection) -> int:
    if not NOTIFY_TARGET:
        return 0
    failures = 0
    rows = database.execute("""
        SELECT capture_id, task_id, source_name, archived_path
        FROM captures
        WHERE status = 'confirmed' AND notified_at IS NULL AND task_id IS NOT NULL
        ORDER BY created_at
    """).fetchall()
    for capture_id, task_id, source_name, archived_path in rows:
        if (QUEUE_DIR / source_name).exists():
            continue
        try:
            archive = Path(archived_path)
            if archive.suffix.lower() in AUDIO_SUFFIXES:
                transcript = read_stable(archive.with_name(archive.name + ".transcript.txt")).decode("utf-8")
            else:
                _, transcript, _ = parse_envelope(read_stable(archive), source_name)
            notify(capture_id, task_id, transcript)
            database.execute(
                "UPDATE captures SET notified_at = ?, updated_at = ? WHERE capture_id = ?",
                (time.time(), time.time(), capture_id),
            )
            database.commit()
            print(f"Delivered pending receipt for {capture_id} as {task_id}")
        except (OSError, subprocess.CalledProcessError, CaptureError) as error:
            failures += 1
            print(f"Voice receipt retry failed for {capture_id}: {error}", file=sys.stderr)
    return failures


def consume_queue(transcriber: Callable[[Path], str] | None) -> int:
    with closing(connect_database()) as database:
        failures = retry_orphaned_notifications(database)
        # Only audio has a durable transcription recovery contract. Preserve
        # legacy text retry behavior and never treat raw archives as queue files.
        pending = database.execute("""
            SELECT source_name, archived_path FROM captures
            WHERE status != 'confirmed' ORDER BY created_at
        """).fetchall()
        for source_name, archived_path in pending:
            source, archive = QUEUE_DIR / source_name, Path(archived_path)
            if archive.suffix.lower() not in AUDIO_SUFFIXES or source.exists() or source.is_symlink():
                continue
            try:
                if Path(source_name).name != source_name or archive.parent != ARCHIVE_DIR:
                    raise CaptureError("Unsafe archived receipt path")
                process_capture(database, archive, transcriber, source_path=source)
            except (OSError, sqlite3.Error, subprocess.CalledProcessError,
                    ValueError, CaptureError) as error:
                failures += 1
                print(f"Voice recovery failed for {source_name}: {error}", file=sys.stderr)
        for path in queue_files():
            try:
                task_id = process_capture(database, path, transcriber)
                print(f"Confirmed {path.name} as {task_id}")
            except (OSError, sqlite3.Error, subprocess.CalledProcessError,
                    ValueError, CaptureError) as error:
                failures += 1
                print(f"Voice capture failed for {path.name}: {error}", file=sys.stderr)
    return 1 if failures else 0


def main(transcriber: Callable[[Path], str] | None = None) -> int:
    try:
        queue, state = QUEUE_DIR.resolve(), STATE_DIR.resolve()
        if queue == state or queue in state.parents or state in queue.parents:
            raise CaptureError("Queue and state directories must not overlap")
        for path in (STATE_DIR, ARCHIVE_DIR, DATABASE_PATH, STATE_DIR / "consumer.lock",
                     Path(str(DATABASE_PATH) + "-wal"), Path(str(DATABASE_PATH) + "-shm")):
            if path.is_symlink():
                raise CaptureError(f"Refusing symlink state path: {path.name}")
        if QUEUE_DIR.is_symlink():
            raise CaptureError("Refusing symlink queue directory")
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with os.fdopen(os.open(STATE_DIR / "consumer.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 0
            return consume_queue(transcriber)
    except (OSError, sqlite3.Error, CaptureError) as error:
        print(f"Voice queue failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
