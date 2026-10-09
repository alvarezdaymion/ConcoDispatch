# Design: simple capture, durable intake

## Paths

```text
iPhone Action Button → Record Audio → Stop → named audio file
                                               │ iCloud sync
Mac Hammerspoon (15s) → receiver → raw archive + SQLite receipt
                                → offline transcript sidecar
                                → Hermes create + exact body readback
                                → optional receipt → remove unchanged source

Legacy phone text → same queue/ledger → original text creation behavior
Mac hold-backslash → Dictate Text → Stop → AppleScript → Hermes Triage
```

Hammerspoon remains the scheduler. No extra background daemon or silence detector is introduced. The Mac trigger stays unchanged; the audio fix targets the phones.

## Identity

The mobile Shortcut combines a millisecond timestamp and random number after recording ends. Set Name connects that identity to the audio file; Save File receives a literal queue folder rather than a tokenized destination filename. It starts recording immediately and finishes On Tap, with no configured duration limit.

Audio IDs are recovered from filenames. The receiver accepts doubled audio extensions and numbered duplicate suffixes, preserving one capture identity. It rejects invalid IDs, symlink inputs, overlapping queue/state paths, and reuse of an identity with different bytes. Comma-formatted random values remain compatible with Apple's locale formatting.

Supported audio suffixes: `.m4a`, `.wav`, `.mp3`, `.caf`, `.aiff`. The phone source produces `.m4a`; doubled extensions are tolerated. Generated action UUIDs connect workflow actions, not machine or account identities.

The text baseline remains rebuildable with `--capture-mode dictation`. It writes:

```text
VOICEKANBAN/2
capture_id: capture-example-0001
captured_at: 2026-01-01T10:00:00Z
---
Draft a project outline.
```

`VOICE_KANBAN_ENVELOPE_MARKER` preserves a deployed text marker. Plain text without the configured marker retains the original filename-plus-bytes SHA-256 identity. Do not rename legacy recovery files or reset the ledger.

## Audio lifecycle

1. Acquire a nonblocking advisory lock in the state directory. Another receiver pass exits without work.
2. Read a regular, nonsymlink source and check file identity/size/timestamps before and after the read.
3. Atomically archive the exact bytes locally, fsync the file and directory, and commit an `archived` SQLite receipt before transcription.
4. Transcribe the archived file with the optional local `faster-whisper` model. Runtime model loading is offline-only, CPU/int8, English `base.en`. There is no network/cloud fallback.
5. Persist the entire transcript as a fsynced sidecar before any task creation. Reuse it across retries and process restarts.
6. Create a card with a short title, full transcript via `--body-file`, assignee `default`, creator `iphone-voice-capture`, and key `iphone-voice-capture:<capture_id>`.
7. Read the exact task back using native `kanban show --json`. Verify task identity and exact body before marking the receipt confirmed.
8. Send an optional receipt if configured, then hash-check the source again. Remove only the unchanged queue file. The local recording and transcript remain archived.

Failures retain source/archive state and record attempt counts plus the last processing error where a receipt exists. A missing or blank transcript creates no task. Pending audio receipts can recover from the archive even if the queue source disappeared. A create whose response was lost retries with the same identity and cached transcript.

The existing SQLite schema is preserved. Old confirmed text rows do not need migration. Legacy text preserves its baseline semantics: its create response supplies confirmation without the new independent audio body readback. Unconfirmed orphaned legacy text still requires restoring its original queue source for manual recovery.

## Recovery boundaries

- Inspect the task, receipt, archive, and source before repeating a real request.
- Never overwrite a collision archive or delete receipts to force progress.
- Do not edit a durable transcript sidecar after task creation; it is the exact body used for readback and retries.
- Optional receipt retries can repeat a message after an uncertain send response. Enabling a destination later can send historical unnotified confirmations, including short transcript summaries; review that scope deliberately.
- Recordings are retained locally indefinitely. There is no automatic purge in this version.
- Native Hermes idempotency is a retry-safety mechanism, not a distributed exactly-once guarantee. Archived/removed tasks and externally edited cards can invalidate assumptions.
- Stable reads detect changes during a read, not every possible partially synced file. iCloud may delay delivery, and a stalled CLI/transcription process can stall polling. Physical-device and sync tests are necessary.

## Frozen deployment

`scripts/install_snapshot.py` installs regular, tracked runtime source from a clean committed revision into a commit-named directory. It excludes settings, recordings, environments, and state. `SOURCE.json` binds the commit, tree, and file hashes; reinstall verifies existing snapshot contents instead of overwriting them.

Dependencies and private config stay outside the snapshot. Point Hammerspoon at the frozen path rather than an actively edited branch checkout. A snapshot installed from an unmerged fix branch is a validation deployment, not a claim that the fix is on `main`.

## Verification

The synthetic suite covers archival ordering, transcript persistence, retry/restart/orphan recovery, duplicate extensions, full body readback, source mutation, locks, local model behavior, legacy text compatibility, builder structure, and snapshot identity. It uses explicit mocks where appropriate and does not prove the physical phone.

Real audio/transcription plus an isolated real Hermes board is a separate integration check. Shortcut signing/import, editor rendering, Shortcuts sync, microphone permissions, locked-phone launch, long recording, and gateway task execution are separate gates. Use [the phone checklist](phone-tests.md) for the final operator test.
