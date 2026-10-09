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

Keep existing shell config trusted and private. Existing settings are authoritative, including custom queue/state paths and notification destinations. Apple transcription is the only supported backend. If an existing configuration is incompatible, stop with the precise reason; do not replace it with example defaults or guess historical routing.

## 2. Prepare, without enabling intake

```sh
python3 scripts/setup.py --prepare
```

This builds and signs the native receiver app, installs a commit-frozen runtime, explicitly prepares/checks speech assets at the final helper path, generates a signed phone Shortcut, and writes the receiver definition. It does not load a LaunchAgent, import a Shortcut, send a notification, submit a task, or start a Hermes worker. Inspect the installed definition and run `--check` for remaining readiness failures.

The prepared definition stays at `VOICE_KANBAN_STATE_DIR/receiver.plist`, outside launchd's login-discovery directories. Only `--activate` installs it into `~/Library/LaunchAgents/` and loads it; subsequent logins can then start the explicitly activated receiver.

Use `--hermes-bin` with the absolute installed CLI path when it is not at the default `~/.local/bin/hermes`. `--profile`, `--board`, `--assignee` and `--locale` select new-install settings; conflicting overrides on existing config are refused. `--config` selects an existing trusted shell file. `--home` redirects preparation into a test home and forbids activation/import, but native signing and speech preparation still use the Mac's tools and asset services.

Source must be a clean committed revision. For development, prepare only an isolated committed fixture or candidate clone, not a mutable checkout. Native assets can require network access during this explicit preparation step; normal transcription never downloads them.

The installer generates private `config.sh`; there is no separate example configuration to copy. It installs only the consumer, transcription adapter, package marker and shell wrapper in the commit-frozen runtime, plus `SOURCE.json` recording source identity and hashes. Setup tools, builders and tests remain in the repository. Swift inputs are read from that same Git commit into temporary build files, compiled, then discarded. Keep installed snapshots unedited, including bytecode caches; reuse verifies their complete path set and hashes rather than overwriting them.

Local app signing does not require an Apple developer account. The optional signing-identity flag supports an existing local signing identity. A changed app signature can require renewed OS consent on an upgrade; never defeat that protection.

### Existing installations

Do not rebuild beneath a loaded receiver. Inspect the exact `io.concodispatch.receiver` definition first. Only when it belongs to this installation and the approved maintenance window is ready, unload that exact service:

```sh
launchctl bootout "gui/$(id -u)/io.concodispatch.receiver"
```

Prepare the new version, then activate explicitly. Preserve the previous app, definition and helper as rollback material before an upgrade; retain all source snapshots and the existing config/state. If preparation fails, do not activate incomplete files: restore the previous binaries/definition and bootstrap the previous service. Never kill unrelated apps/services or discard receipts to make setup pass.

Existing speech helper bytes are reused, not upgraded automatically. Older/unrecognized service definitions require manual migration. The queue must be a subfolder of the Shortcuts iCloud workflow container. Changing settings or signing identity for an existing commit build requires manual review; setup refuses to overwrite that build.

Disable any previous queue scheduler separately before activation. Do not remove unrelated hotkeys or change login settings. The advisory receipt lock is a safety net, not permission to keep competing schedulers.

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

Test each phone after its Shortcut has synced:

- Start with a short, harmless request. Tap Stop and confirm one task contains the full transcript and the worker's acknowledgment.
- Record for several minutes with a thinking pause and distinct opening/closing phrases. Recording must continue until Stop, and both phrases must reach the task.
- Check locked-phone launching separately. A working unlocked test does not prove locked-device permissions.
- If nothing arrives, inspect sync, receiver logs and the receipt before repeating the request. Do not reset receipts to force delivery; see [recovery](#troubleshooting-and-recovery) below.

A clean clone plus isolated output home proves packaging without old config, not a second Apple account, a fresh Mac, or new phone consent. Synthetic recordings do not prove phone microphone capture or phone-side sync.

## Optional Mac audio capture

The Mac Shortcut records audio into the same configured queue. From the repository root, generate and sign it:

```sh
python3 -m voice_kanban.build_shortcut --platform mac-audio --queue-folder 'VoiceKanbanInbox/'
shortcuts sign --mode anyone --input 'dist/ConcoDispatch Mac.unsigned.shortcut' --output 'dist/ConcoDispatch Mac.shortcut'
open 'dist/ConcoDispatch Mac.shortcut'
```

Use the actual configured queue folder if it differs. Preserve an existing Shortcut's identity instead of importing a duplicate. Launch it from Shortcuts or assign a native keyboard/menu-bar gesture; no separate scheduler is needed.

## Troubleshooting and recovery

Inspect `receiver.log`, `receiver-error.log`, `receipts.sqlite3`, and `archive/` under the configured `VOICE_KANBAN_STATE_DIR`. Keep their contents private. If delivery is missing, first establish whether the recording synced, was archived, was transcribed, and has a confirmed task.

- **No synced recording:** check iCloud/Shortcuts sync and the exact queue folder. Keep the Mac awake and logged in. A partially synced file or saved notification is not delivery proof.
- **Archived but not delivered:** fix the recorded error, unavailable helper/assets or stopped gateway. Pending audio can retry from its archive even if the queue file disappeared. Recognition and CLI calls have deadlines; uncertain creates retain the same capture identity and cached transcript.
- **Missing or changed transcript:** restore its verified original under `archive/.transcripts/`. Never edit it after task creation, clear a pinned digest or retranscribe an uncertain create. Compare the task body and receipt before restoring anything.
- **Collision or interrupted cleanup:** never overwrite an archive, rename a capture to force a new identity, or delete receipts. Inspect hidden `.cleanup-*` queue directories after a crash; retained files require manual comparison with the archive and receipt before restoring them. Do not overwrite a newer arrival.
- **Older installations:** preserve original profile/board settings during the first upgraded pass, existing text markers and ledgers. Old orphaned text captures need their original queue source restored. Flat legacy transcript caches require verified provenance; an unrelated file is not a recovery transcript. Do not reset state to bypass migration checks.
- **Optional notifications:** intake confirmation and message delivery are separate. An uncertain send may repeat a message; enabling a destination can send historical confirmations containing transcript summaries. Inspect that scope before enabling it.

Recordings and transcripts are retained indefinitely; there is no automatic purge. Hermes retry identities reduce duplicates, but do not guarantee exactly-once execution across archived/deleted tasks or externally edited cards. Back up config, archives and receipts before maintenance and preserve the previous working installation for rollback.

## Developer verification

Run `make check` for isolated tests, source generation and shell syntax; generated configuration is syntax-checked in the setup tests. On a compatible Mac, `make native` compiles both Swift executables. Canonical tests do not download assets, import Shortcuts, activate services or touch live boards/queues.

The opt-in `scripts/test_audio_integration.py` harness checks real local transcription, exact task-body readback and duplicate-free replay on an isolated Hermes board; use `--help` for its required synthetic-audio, helper, CLI and expected-phrase arguments. Prepare/check speech assets at the final helper path first. `NATIVE_SPEECH_PROOF=1 python3 -m unittest discover -s tests -p test_native_speech.py -v` generates a synthetic long recording using `say` and ffmpeg. Neither check proves physical-phone capture, iCloud sync, scheduled permissions or automatic worker execution.
