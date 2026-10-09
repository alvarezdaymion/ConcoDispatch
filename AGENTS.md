# Working in this repository

## Scope and compatibility

- Support Python 3.9+ for source generation and tests. Optional audio dependencies are pinned in `requirements-audio.txt`.
- Preserve Mac direct `--triage` creation separately from mobile `--assignee default` creation.
- Keep the mobile idempotency key `iphone-voice-capture:<capture_id>` stable. Archive before create, retain changed sources, and retry uncertain creates with the same key.
- A queued notification must not imply Kanban confirmation.
- Use home-relative defaults and `VOICE_KANBAN_*` configuration. Preserve existing receipt ledgers when updating.

## Verification

- Run `make check` before submitting a change. On macOS, also compile the AppleScript without running it: `osacompile -o .local/mac_capture.scpt shortcuts/mac_capture.applescript`.
- Keep tests synthetic and isolated under `.local/`. Stub Hermes; never touch a live board, gateway, cloud queue, or notification destination.
- Do not import Shortcuts, reload Hammerspoon, run generated AppleScript, or deploy runtime files during tests.
- Source generation and mocked tests do not prove microphone capture, physical-device behavior, iCloud synchronization, delivery, or gateway execution. Document those limits explicitly.

## Repository hygiene

- Submit changes through pull requests. Do not force-push, direct-push to the default branch, or merge without explicit authorization.
- Keep source, comments, and documentation technical and portable. Exclude session notes and deployment-specific status.
- Do not commit machine paths, account/device IDs, live destinations, credentials, transcripts, recordings, databases, local settings, or generated Shortcut binaries.
- Review the diff and staged paths before committing. `.gitignore` is not a security boundary.
