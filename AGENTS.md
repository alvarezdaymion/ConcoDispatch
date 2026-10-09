# Working in this repository

## Scope and compatibility

- Support Python 3.9+ for source generation and tests. Optional audio dependencies are pinned in `requirements-audio.txt`.
- Preserve legacy Mac direct `--triage` separately from shared audio intake. New audio captures use the configured assignee (default `default`).
- Launchd owns queue scheduling; Hammerspoon is an optional legacy Mac trigger only. Do not reintroduce a queue timer there.
- Native speech asset download requires explicit `--prepare`. Normal transcription must remain local, bounded, and download-free; retain Whisper as an explicit compatibility backend.
- Pin explicit board/profile routing on new deployments and preserve each receipt's original routing during retries.
- Keep the mobile idempotency key `iphone-voice-capture:<capture_id>` stable. Archive before create, retain changed sources, and retry uncertain creates with the same key.
- A queued notification must not imply Kanban confirmation.
- Use home-relative defaults and `VOICE_KANBAN_*` configuration. Preserve existing receipt ledgers when updating.

## Verification

- Run `make check` before submitting a change. On macOS, also compile the AppleScript without running it: `osacompile -o .local/mac_capture.scpt shortcuts/mac_capture.applescript`.
- Keep canonical tests synthetic and isolated under `.local/` with stubbed Hermes. Opt-in audio integration may use a real CLI with an isolated `HOME`, `HERMES_HOME` and `HERMES_KANBAN_DB`; never touch a live board, gateway, cloud queue, or notification destination.
- Do not import Shortcuts, reload Hammerspoon, run generated AppleScript, or deploy runtime files during tests.
- Source generation and mocked tests do not prove microphone capture, physical-device behavior, iCloud synchronization, delivery, or gateway execution. Document those limits explicitly.

## Repository hygiene

- Submit changes through pull requests. Do not force-push, direct-push to the default branch, or merge without explicit authorization.
- Keep source, comments, and documentation technical and portable. Exclude session notes and deployment-specific status.
- Do not commit machine paths, account/device IDs, live destinations, credentials, transcripts, recordings, databases, local settings, or generated Shortcut binaries.
- Review the diff and staged paths before committing. `.gitignore` is not a security boundary.
