# Design: simple capture, durable intake

## Paths

```text
iPhone button / Mac native Shortcut → Record Audio → Stop → named audio file
                                               │ iCloud sync
Mac launchd (15s) → receiver → raw archive + SQLite receipt
                                → offline transcript sidecar
                                → Hermes create + exact body readback
                                → remove unchanged source → optional receipt batch

Legacy phone text → same queue/ledger → original text creation behavior
Mac hold-backslash → Dictate Text → Stop → AppleScript → Hermes Triage
```

Launchd schedules nonoverlapping one-shot receiver passes. New Mac audio and phone audio share intake; legacy Mac dictation remains a separate direct-Triage option. Hammerspoon is an optional legacy trigger, never a receiver dependency. No silence detector is used.

## Identity

The mobile Shortcut combines a millisecond timestamp and random number after recording ends. Set Name connects that identity to the audio file; Save File receives a literal queue folder rather than a tokenized destination filename. It starts recording immediately and finishes On Tap, with no configured duration limit.

Audio IDs are recovered from filenames. The receiver accepts doubled audio extensions and numbered duplicate suffixes, preserving one capture identity. It rejects invalid IDs, symlink inputs, overlapping queue/state paths, and reuse of an identity with different bytes. Comma-formatted random values remain compatible with Apple's locale formatting.

Supported audio suffixes: `.m4a`, `.wav`, `.mp3`, `.caf`, `.aiff`. The phone source produces `.m4a`; doubled extensions are tolerated. Generated action UUIDs connect workflow actions, not machine or account identities.

The alternative text workflow is rebuildable with `--capture-mode dictation`. It writes:

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
4. Transcribe the archived file using an explicitly selected local backend. Apple SpeechAnalyzer/SpeechTranscriber uses prepared on-device assets on supported macOS 26+ systems. `--check` never downloads; only explicit `--prepare` may provision assets. Compatibility Whisper uses offline-only CPU/int8 English `base.en`. Both run in subprocesses with a positive finite deadline (default 600 seconds); no network/cloud fallback is permitted.
5. Persist the entire transcript as a fsynced sidecar under `archive/.transcripts/`, separate from raw capture filenames. Bind its SHA-256 to the receipt before task creation and validate it on retries and notification recovery.
6. Commit routing alongside the new receipt, then create a card with a short title, full transcript via `--body-file`, configured assignee (default `default`), creator `iphone-voice-capture`, and stable key `iphone-voice-capture:<capture_id>`. Shared Mac audio deliberately uses the same historical key namespace. Explicit profile/board routing is reused for create and readback even if configuration changes during a retry. Historical receipts lack routing evidence: preserve their original board/profile configuration during the first upgraded pass. Omitted profile/board retains legacy ambient routing; new deployments should pin both.
7. Read the exact task back using native `kanban show --json`. Verify task identity and exact body before marking the receipt confirmed.
8. Atomically move the source into a unique hidden `.cleanup-*` directory inside the queue, then verify and remove that claimed file. A new arrival at the original pathname is left alone. Restore a changed claimed file without overwriting a concurrent arrival; retain it for manual recovery if restoration fails. The local recording and transcript remain archived. After all intake, attempt optional message receipts with bounded CLI calls (default 30 seconds). Message failures no longer retain confirmed queue sources or run ahead of healthy captures; unnotified confirmations retry from archives. Each pass can still spend bounded time delivering its receipt batch.

Failures retain source/archive state and record attempt counts plus the last processing error where a receipt exists. A missing or blank transcript creates no task. Pending audio receipts can recover from the archive even if the queue source disappeared. A create whose response was lost retries with the same identity and cached transcript.

The receiver upgrades SQLite ledgers transactionally without resetting receipts, adding nullable `transcript_sha256` and a durable `legacy_transcript_eligible` flag. Only audio receipts already present in a pre-namespace ledger (one lacking both columns) gain eligibility to import flat legacy sidecars. New receipts and receipts in ledgers already using `transcript_sha256` remain ineligible, including retries with no digest or a missing cache. Eligible sidecars are copied into `archive/.transcripts/` only when they are not another receipt's raw text archive; an unowned flat file alone never grants eligibility. Binding the first valid transcript digest also clears eligibility, so uncertain creates retry with the pinned namespaced cache and the same idempotency key.

Historical caches have no prior digest, so migration cannot detect modifications made before first binding. A ledger already upgraded by a version without the eligibility flag cannot reliably distinguish remaining old sidecars from unrelated raw archives; those sidecars are not automatically imported. If recovery requires such a cache, verify its provenance and restore the original into the namespaced location rather than clearing a pinned digest or resetting the ledger. Old confirmed text rows keep their semantics: the create response supplies confirmation without independent audio body readback. Unconfirmed orphaned legacy text still requires restoring its original queue source for manual recovery.

## Recovery boundaries

- Inspect the task, receipt, archive, and source before repeating a real request.
- Never overwrite a collision archive or delete receipts to force progress.
- Do not edit a durable transcript sidecar after task creation; it is the exact body used for readback and retries.
- If a pinned transcript is missing or changed, restore the original rather than retranscribing an uncertain create. Corrupt pending notifications record an error but do not prevent healthy queue entries from processing.
- After a crash during cleanup, inspect hidden `.cleanup-*` queue directories. Retained files are not automatically requeued; compare the archive and receipt before restoring them. Queue writers must not edit claimed files in place.
- Optional receipt retries can repeat a message after an uncertain send response. Enabling a destination later can send historical unnotified confirmations, including short transcript summaries; review that scope deliberately.
- Recordings are retained locally indefinitely. There is no automatic purge in this version.
- Native Hermes idempotency is a retry-safety mechanism, not a distributed exactly-once guarantee. Archived/removed tasks and externally edited cards can invalidate assumptions.
- Stable reads detect changes during a read, not every possible partially synced file. iCloud may delay delivery. CLI/transcription deadlines bound stalls while preserving uncertain-create identity and cached bodies. Physical-device and sync tests are necessary.

## Frozen deployment

`scripts/install_snapshot.py` installs regular, tracked runtime source from a clean committed revision into a commit-named directory. It excludes settings, recordings, environments, and state. `SOURCE.json` binds the commit, tree, and file hashes; reinstall verifies the complete path set, rejects symlinks and unexpected additions, and validates file hashes instead of overwriting contents. The receiver wrapper disables bytecode writes to keep frozen trees unchanged. Direct Python invocation of a snapshot must also disable bytecode writes; existing extra files, including caches, require review before reinstallation can verify the snapshot.

Dependencies, the compiled native helper and private config stay outside the snapshot; native Swift source is included. Point the LaunchAgent at the frozen path rather than an actively edited checkout. Generate and lint the plist without loading it during tests. Its per-user service polls with `StartInterval`, runs at login/load, and uses a restrictive umask. Create its state/log directory before bootstrap. Disable the old Hammerspoon queue scheduler during migration; preserve the existing ledger and button bindings. The manifest identifies the installed revision; it does not establish release approval.

## Verification

The synthetic suite covers archival ordering, transcript persistence, retry/restart/orphan recovery, duplicate extensions, full body readback, source mutation, locks, local model behavior, legacy text compatibility, builder structure, and snapshot identity. It uses explicit mocks where appropriate and does not prove the physical phone.

Real audio/transcription plus an isolated real Hermes board is a separate integration check. Shortcut signing/import, editor rendering, Shortcuts sync, microphone permissions, locked-phone launch, long recording, and gateway task execution are separate gates. Use [the phone checklist](phone-tests.md) for the final operator test.
