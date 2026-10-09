#!/usr/bin/env python3
"""Durably bridge iCloud dictation captures into Hermes Kanban."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any

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
                  if path.is_file() and path.suffix.lower() == ".txt")


def read_stable(path: Path) -> bytes:
    before = path.stat()
    payload = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise CaptureError(f"Capture changed while being read: {path.name}")
    return payload


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


def archive_payload(capture_id: str, payload: bytes) -> tuple[Path, str]:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    destination = ARCHIVE_DIR / f"{capture_id}.txt"
    digest = hashlib.sha256(payload).hexdigest()
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise CaptureError(f"Archive collision for capture {capture_id}")
        return destination, digest
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination, digest


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


def process_capture(database: sqlite3.Connection, path: Path) -> str:
    payload = read_stable(path)
    capture_id, transcript, captured_at = parse_envelope(payload, path.name)
    archive_path, digest = archive_payload(capture_id, payload)
    if payload.startswith((ENVELOPE_MARKER + "\n").encode("utf-8")) and path.stem != capture_id:
        raise CaptureError(f"Capture filename {path.stem!r} does not match payload {capture_id!r}")
    now = time.time()
    existing = database.execute(
        "SELECT payload_sha256, status, task_id, notified_at FROM captures WHERE capture_id = ?",
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
        _, status, task_id, notified_at = existing

    if status != "confirmed":
        database.execute(
            "UPDATE captures SET attempts = attempts + 1, updated_at = ? WHERE capture_id = ?",
            (time.time(), capture_id),
        )
        database.commit()
        task = run_json([
            HERMES, "kanban", "create", transcript,
            "--assignee", "default", "--created-by", "iphone-voice-capture",
            "--idempotency-key", f"iphone-voice-capture:{capture_id}", "--json",
        ])
        task_id = task.get("id")
        if not task_id:
            raise CaptureError("Hermes did not return a Kanban task ID")
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

    if path.exists():
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
            payload = Path(archived_path).read_bytes()
            _, transcript, _ = parse_envelope(payload, source_name)
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


def main() -> int:
    with connect_database() as database:
        failures = retry_orphaned_notifications(database)
        for path in queue_files():
            try:
                task_id = process_capture(database, path)
                print(f"Confirmed {path.name} as {task_id}")
            except (OSError, sqlite3.Error, subprocess.CalledProcessError,
                    json.JSONDecodeError, CaptureError) as error:
                failures += 1
                print(f"Voice capture failed for {path.name}: {error}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
