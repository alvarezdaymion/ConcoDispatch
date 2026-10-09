# Agent-led setup

## Contract

From a clean clone, prepare a local Mac receiver and phone Shortcut using the user's existing Apple and Hermes accounts. Keep the phone interaction **launch → speak → tap Stop → automatic submission**. Preserve existing configuration, recordings, receipts, routing and Shortcut identities. No account credentials belong in this repository or chat.

Setup has four explicit phases. An agent can perform them from one setup request, but must distinguish preparation from enabling real task execution. Never report a working phone installation from compilation or mocked checks alone.

## 1. Inspect prerequisites

```sh
python3 scripts/setup.py --check
```

Native setup requires macOS 26+, a supported Apple speech locale/hardware, Python 3.9+, Git, compatible Swift Command Line Tools, Apple Shortcuts, iCloud Drive/Shortcuts sync, and Hermes with Kanban. Use official [Hermes documentation](https://hermes-agent.nousresearch.com/docs/) for installation or provider setup if missing. Reuse existing authentication; stop at owner-only login, passkey or verification steps. Do not inspect or print credential stores.

Check the intended Hermes profile, board and assignee before enabling intake. A running gateway is required for automatic worker dispatch; an installed CLI alone does not prove this. Do not silently change gateway configuration or restart a working gateway.

Keep existing shell config trusted and private. Existing settings are authoritative, including custom queue/state paths and notification destinations. If a legacy backend or configuration is not supported by automatic preparation, stop with the precise reason and use the documented manual path. Do not replace it with example defaults or guess historical routing.

## 2. Prepare, without enabling intake

```sh
python3 scripts/setup.py --prepare
```

This builds and signs the native receiver app, installs a commit-frozen runtime, explicitly prepares/checks speech assets at the final helper path, generates a signed phone Shortcut, and writes the receiver definition. It does not load a LaunchAgent, import a Shortcut, send a notification, submit a task, or start a Hermes worker. Inspect the installed definition and run `--check` for remaining readiness failures.

The prepared definition stays at `VOICE_KANBAN_STATE_DIR/receiver.plist`, outside launchd's login-discovery directories. Only `--activate` installs it into `~/Library/LaunchAgents/` and loads it; subsequent logins can then start the explicitly activated receiver.

Use `--hermes-bin` with the absolute installed CLI path when it is not at the default `~/.local/bin/hermes`. `--profile`, `--board`, `--assignee` and `--locale` select new-install settings; conflicting overrides on existing config are refused. `--config` selects an existing trusted shell file. `--home` redirects preparation into a test home and forbids activation/import, but native signing and speech preparation still use the Mac's tools and asset services.

Source must be a clean committed revision. For development, prepare only an isolated committed fixture or candidate clone, not a mutable checkout. Native assets can require network access during this explicit preparation step; normal transcription never downloads them.

Local app signing does not require an Apple developer account. The optional signing-identity flag supports an existing local signing identity. A changed app signature can require renewed OS consent on an upgrade; never defeat that protection.

### Existing installations

Do not rebuild beneath a loaded receiver. Inspect the exact `io.concodispatch.receiver` definition first. Only when it belongs to this installation and the approved maintenance window is ready, unload that exact service:

```sh
launchctl bootout "gui/$(id -u)/io.concodispatch.receiver"
```

Prepare the new version, then activate explicitly. Preserve the previous app, definition and helper as rollback material before an upgrade; retain all source snapshots and the existing config/state. If preparation fails, do not activate incomplete files: restore the previous binaries/definition and bootstrap the previous service. Never kill unrelated apps/services or discard receipts to make setup pass.

Automatic preparation supports explicitly configured Apple speech installations only. Whisper remains available through the manual README path. Existing speech helper bytes are reused, not upgraded automatically. Older/unrecognized service definitions require manual migration. The queue must be a subfolder of the Shortcuts iCloud workflow container. Changing settings or signing identity for an existing commit build requires manual review; setup refuses to overwrite that build.

Disable an old Hammerspoon queue scheduler separately before activation. Do not remove unrelated hotkeys or change its login settings. The advisory receipt lock is a safety net, not permission to keep competing schedulers.

## 3. Import only a missing Shortcut

```sh
python3 scripts/setup.py --import-shortcut
```

An existing `ConcoDispatch` is preserved. A same-named import is not an identity-safe update and can break an Action Button binding. Inspect the existing recording/save actions and verify their queue folder matches the active configuration; use native editing with an identity/action backup when an actual upgrade is required. Never write Apple's synced Shortcuts database directly.

For a new Shortcut, complete Apple's import confirmation, wait for iCloud sync, then select it under iPhone Settings → Action Button → Shortcut, or use another existing launch gesture. Run it manually once for microphone/file permissions. Its first action must be **Record Audio**, **Immediately**, **On Tap**. Ask Where To Save and Overwrite must be off. No file picker, transcript review or separate Send step belongs in this flow.

## 4. Activate deliberately

Inspect queued captures and any configured notification destination first: activation can process historical recordings, create real tasks and send previously unnotified confirmations. Do not test on real customer/lead requests.

```sh
python3 scripts/setup.py --activate
```

The per-user LaunchAgent starts the dedicated receiver app through LaunchServices every 15 seconds. The native app runs the same frozen consumer and exits after its pass; it is not another agent or cloud backend. Use Apple's normal permission prompt to grant its iCloud access. Do not grant blanket shell/Python access, modify TCC records, or disable SIP.

Inspect the installed definition and private receiver logs. An interactive shell can have permissions that launchd lacks: verify the actual scheduled identity's iCloud intake. `open -W` waiting for an app to finish does not itself establish successful delivery; the durable receipt and task readback are the authority.

## Verify the real path

Use a harmless diagnostic recording that requests only acknowledgment and no external actions. Check separately:

1. Phone notification means saved/queued, not delivered.
2. Raw audio reaches the Mac and is archived before recognition.
3. The exact full transcript matches the Kanban task body, including its closing phrase.
4. One intended task exists; retries reuse the same capture identity.
5. The gateway claims/spawns the configured worker and produces its real result.

Keep the Mac awake and logged in. iCloud, transcription and dispatcher timing add variable latency. Transcription can be imperfect; task actions retain the agent's own approval boundaries. Confirm the reported final sentence was the actual spoken ending.

Follow [phone acceptance](phone-tests.md) for several-minute capture, thinking pauses and locked-phone tests. A clean clone plus isolated output home proves packaging without old config, not a second Apple account, a fresh Mac, or new phone consent. Treat those evidence layers separately.
