# Working in this repository

This repository preserves the dictation-based baseline in PR #1. Capture changes belong on a separate branch.

## Git workflow

- GitHub is the canonical source. Fetch current `main`, branch, test, push the branch, and open a pull request.
- Do not direct-push, force-push, merge, or enable auto-merge without the owner's explicit authorization. Keep baseline preservation separate from subsequent fixes.
- Keep the repository private until the owner explicitly approves publication. Source should be portfolio-safe from its first commit; no recordings, runtime state, or account-bound exports in history.

- Run `python3 -m unittest discover -s tests -v` and `make shortcuts` before reporting a change complete. Python uses only the standard library; support Python 3.9+.
- Keep tests synthetic and isolated under `.local/`. Stub Hermes rather than touching a real board, gateway, cloud queue, or notification destination.
- Do not import Shortcuts, reload Hammerspoon, run generated AppleScript, or deploy runtime files as part of tests. Shortcuts compilation is not device execution.
- Keep the mobile idempotency key `iphone-voice-capture:<capture_id>` stable. Archive before create; retain a changed source; retry uncertain creates with the same key.
- Preserve Mac direct `--triage` creation separately from mobile `--assignee default` creation. A queued notification must not imply a Kanban confirmation.
- Use home-relative defaults and `VOICE_KANBAN_*` configuration. Do not commit machine paths, account/device IDs, live destinations, credentials, transcripts, databases, or generated Shortcut binaries.
- Review `git diff` and `git status` for privacy before staging. Runtime data belongs outside Git; `.gitignore` is not a security boundary.
- Document behavior gaps honestly. A mocked passing test is not proof of Apple dictation, iCloud sync, delivery, or gateway execution.
