# Working in this repository

## Scope and compatibility

- Support Python 3.9+ for source generation and tests, using the standard library only.
- Phone and Mac audio share the same intake and configured assignee (default `default`). Launchd owns queue scheduling.
- Apple speech asset download requires explicit `--prepare`. Normal transcription must remain local, bounded, and download-free.
- Preserve existing text-capture recovery and ledger migrations; new Shortcuts generate audio only.
- Pin explicit board/profile routing on new deployments and preserve each receipt's original routing during retries.
- Keep the mobile idempotency key `iphone-voice-capture:<capture_id>` stable. Archive before create, retain changed sources, and retry uncertain creates with the same key.
- A queued notification must not imply Kanban confirmation.
- Use home-relative defaults and `VOICE_KANBAN_*` configuration. Preserve existing receipt ledgers when updating.

## When asked to set this up

- Read `docs/setup.md`, run `python3 scripts/setup.py --check`, and resolve the reported prerequisites using official tools/docs. Reuse the user's configured Hermes and Apple accounts; stop for owner authentication or phone-only confirmations. Never ask for secrets in chat.
- Use the explicit setup CLI preparation, import and activation phases. Preparation alone must not load a service, import a Shortcut, submit a test task or restart the Hermes gateway. A setup request permits the agent to perform these phases deliberately, after inspecting the actual queue and routing.
- Preserve existing configuration bytes, receipt state, recordings and same-named Shortcut identities. Refuse unsupported upgrades rather than silently changing backends, routing or button bindings. Do not overwrite a running receiver's code.
- Verify iCloud access under the scheduled native app identity, exact full task body and real worker kickoff. Queued notifications, compilation, fake homes and mocked tools are not physical-phone proof. Use a harmless diagnostic request only when its real execution is authorized.

## Verification

- Run `make check` before submitting a change. On a compatible Mac, also run `make native`.
- Keep canonical tests synthetic and isolated under `.local/` with stubbed Hermes. Opt-in audio integration may use a real CLI with an isolated `HOME`, `HERMES_HOME` and `HERMES_KANBAN_DB`; never touch a live board, gateway, cloud queue, or notification destination.
- Do not import Shortcuts, activate services, or deploy runtime files during tests.
- Source generation and mocked tests do not prove microphone capture, physical-device behavior, iCloud synchronization, delivery, or gateway execution. Document those limits explicitly.

## Repository hygiene

- Submit changes through pull requests. Do not force-push, direct-push to the default branch, or merge without explicit authorization.
- Keep source, comments, and documentation technical and portable. Exclude session notes and deployment-specific status.
- Do not commit machine paths, account/device IDs, live destinations, credentials, transcripts, recordings, databases, local settings, or generated Shortcut binaries.
- Review the diff and staged paths before committing. `.gitignore` is not a security boundary.
