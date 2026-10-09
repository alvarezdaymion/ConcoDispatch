# Security and data handling

## Trust boundaries

ConcoDispatch turns queue files into agent tasks. Treat the queue, receiver configuration, and local state as trusted inputs, not as an unauthenticated upload service. Anyone able to write a queue file can submit work to the configured agent. Review that agent's permissions before enabling intake.

- Shared phone/Mac audio passes through the configured Apple account's iCloud Drive. Transcription runs locally using explicitly prepared Apple speech assets or a provisioned Whisper model; queue processing never downloads models or falls back to cloud transcription.
- The local archive retains recordings and transcript sidecars indefinitely. SQLite receipts store task identifiers and processing errors. Task bodies also persist in the configured Kanban system.
- Keep state outside the checkout, restrict access with filesystem permissions, and consider backups part of the same data boundary. The receiver does not encrypt or automatically purge these files.
- `config.sh` is executable shell configuration. Source only trusted files and keep notification destinations private.
- Setup builds a dedicated locally signed receiver app for macOS file-access consent. Grant only that app's required access through the normal OS flow. Compilation and interactive CLI access do not prove launchd's privacy permissions; never write TCC records or grant blanket shell/Python access to bypass a failure.
- Preparation does not activate intake or import Shortcuts. Activation can process existing queued work and historical optional notifications; inspect those inputs and agent permissions first. Back up an existing app/helper/definition before an approved stopped-service upgrade, leaving config, archives and receipts intact.
- Optional notifications contain a short transcript summary. Enabling a destination can deliver historical, previously unnotified confirmations. Sends occur after intake/cleanup and use bounded CLI calls.
- Ignore rules prevent accidental staging of common runtime files; they do not remove already tracked data or sanitize recordings.

## Reporting vulnerabilities

Do not post credentials, recordings, transcripts, private task details, account identifiers, or exploitable live-system details in an issue or pull request. Use GitHub private vulnerability reporting when available, or an established private channel to the maintainer. For public bug reports, use synthetic fixtures and include the affected revision plus minimal reproduction steps.

If a credential is exposed, revoke or rotate it first. Removing it from the current source does not remove copies from Git history, pull requests, or clones.
