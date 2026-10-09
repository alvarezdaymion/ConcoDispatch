# Design: preserve dictation, make intake inspectable

## Two paths, deliberately different

```text
iPhone Action Button → Dictate Text → Stop → envelope text file
                                               │ iCloud sync
Mac Hammerspoon (15s) → consumer → local archive + SQLite receipt
                                  → Hermes create (default assignee)
                                  → optional receipt → remove unchanged source

Mac hold-backslash → Dictate Text → Stop → AppleScript → Hermes create (Triage)
```

The package extracts the queue consumer, mobile builder, Mac action chain, and Hammerspoon trigger into source-controlled, configurable files. It does not replace dictation with audio capture or change board routing. Hammerspoon remains the scheduler; there is no additional daemon.

## Envelope and identity

Synthetic example, saved as `capture-example-0001.txt`:

```text
VOICEKANBAN/2
capture_id: capture-example-0001
captured_at: 2026-01-01T10:00:00Z
---
Draft a project outline.
```

The mobile Shortcut combines a millisecond timestamp and random number to produce a capture ID, puts that same ID inside the envelope and filename, and saves to a **literal folder**. It does not build a filename inside Save File's folder field. Comma-formatted random numbers are accepted because Apple may format numbers by locale.

`VOICE_KANBAN_ENVELOPE_MARKER` allows a local deployment to retain an existing envelope marker without embedding it in public source. The default is `VOICEKANBAN/2`. All text not starting with the configured marker is treated as legacy plain text; its ID is a SHA-256 digest of the original filename plus payload. Preserve filenames when recovering legacy files.

## Mobile receipt lifecycle

1. Read each `.txt` file without changing or renaming the iCloud source. Compare size/mtime before and after the read.
2. Decode and validate the envelope. Atomically replace a local archive file after flushing and fsyncing its bytes. Reject reuse of the ID with different archive contents.
3. Reject a mismatched envelope filename before creating a card. The baseline performs this check after archival.
4. Commit an `archived` receipt to SQLite before calling Hermes.
5. Call `hermes kanban create` with `--assignee default`, `--created-by iphone-voice-capture`, and the stable key `iphone-voice-capture:<capture_id>`.
6. Store the returned task ID as `confirmed`. This status means the CLI returned an ID; the baseline does not perform an independent board readback.
7. If configured, send a receipt and commit `notified_at`. A failed receipt retains the source. If the source later disappears, retry that receipt from the archive without recreating the card.
8. Compare the source bytes with the archive hash again, then delete only the unchanged source. Any changed content survives for operator review.

Retries after uncertain create responses reuse the same idempotency key. A replay of a confirmed capture does not call create again. Processing continues past per-file failures; the pass exits nonzero if any fail. SQLite stores attempt counts; errors go to stderr rather than a durable error log.

This is retry-safe intake, not a distributed exactly-once guarantee. The stable-read check cannot prove that a sync write is finished between polls. A single Hammerspoon instance serializes its subprocesses, but there is no global lock. A stalled Hermes command can stall polling. An unconfirmed archive whose queue source disappears is retained for manual recovery, not automatically resubmitted.

## Recovery

- First inspect the card, queue file, receipt, and archive. Never delete state to “reset” delivery; that removes local replay history.
- For an unconfirmed archived capture with no source, restore the original bytes under the original filename in the queue, using the same marker and state directory. The stable idempotency key permits a safe retry only if the Hermes board preserves its own idempotency record.
- For a collision or source-changed error, preserve both versions and resolve identity deliberately. Do not overwrite the archive to force progress.
- Turning on notifications after running without them sends pending receipts for previously confirmed captures. Review the destination and historical scope first.

## Shortcut source map

`python3 -m voice_kanban.build_shortcut --platform mobile` builds:

1. Dictate Text, English, start immediately, stop **On Tap**.
2. If Dictated Text has a value: current date → custom date format → random number → Capture ID text.
3. Envelope text referencing the ID, date, and dictated text → Set Name to the ID plus `.txt`.
4. Save File to `VoiceKanbanInbox/`, ask off, overwrite off → queued notification.
5. Otherwise: nothing-captured notification.

`--platform mac` builds the current Mac action chain:

1. Dictate Text, English, start immediately, stop **On Tap**.
2. Run AppleScript with Dictated Text as input, using `shortcuts/mac_capture.applescript`.
3. Stop and Output the AppleScript result.

The AppleScript resolves Hermes from the private config, then `PATH`, then a home-relative installation. It shell-quotes the transcript and preserves `--triage --created-by mac-voice-capture --json`. Empty input does not create a card.

Action UUIDs are generated at build time. They connect actions within a workflow; they are not exported machine or account IDs. Generated binaries and signing artifacts stay under ignored `dist/`.

## Verification boundaries

The standard-library suite covers archive-before-create, uncertain-response retries, legacy recovery, locale IDs, a ten-capture burst with replay, orphaned notification retries, filename mismatch, source mutation, configurable marker/folder, and both workflow structures. Tests use isolated synthetic fixtures and fake subprocess responses, not a real board.

AppleScript can be compiled without running it. Hammerspoon syntax can be checked with `luac -p hammerspoon/voice_kanban.lua` when Lua is installed. Neither proves device-level operation; the setup guide provides the manual acceptance checks.
