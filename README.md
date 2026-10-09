# ConcoDispatch

**Launch. Explain the task. Tap Stop. An agent gets the complete recording as a task.**

A small Apple Shortcuts bridge for [Hermes Agent Kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban). Record first, transcribe locally, then submit the full transcript through a durable receiver.

```text
iPhone Action Button ─┐
Mac native Shortcut ──┴→ Record Audio → Stop → iCloud queue
                                                  ↓
Mac launchd → archive + receipts → local transcription → Hermes task + readback
```

**No Hammerspoon requirement. No transcription account or per-minute API bill.** The default phone handoff uses the user's existing Apple account; task execution uses their existing configured Hermes agent/provider. Audio is retained locally for recovery.

## Product direction

The intended end state is **clone → tell your agent “set this up” → usable voice-to-Kanban kickoff**, with only unavoidable permission/device confirmations. This revision refactors the runtime before adding that installer. Setup is still explicit; downloading the repo does not install a service or import a Shortcut.

## Included and requirements

- Phone and new Mac audio Shortcuts share the same queue, archives, transcript cache, receipts and retry-safe task creation.
- A launchd definition replaces Hammerspoon's queue timer. It polls every 15 seconds without overlapping receiver passes.
- Native Apple speech on supported macOS 26+ hardware/languages; a small Swift helper uses SpeechAnalyzer/SpeechTranscriber. Assets are prepared explicitly, never downloaded during queue processing.
- Optional offline Whisper `base.en` backend for compatibility. No silent fallback between backends or to cloud STT.
- The legacy `--platform mac` dictation-to-Triage Shortcut and optional Hammerspoon hold-backslash trigger remain separate compatibility options. Hammerspoon no longer polls the queue or changes its own login settings.

You need an awake, logged-in Mac, Python 3.9+, Hermes with Kanban and a configured worker profile, and a running Hermes gateway for actual kickoff. Phone capture also requires iCloud Drive/Shortcuts sync under the same Apple account. Native speech compilation requires a compatible Swift SDK/Command Line Tools. Initial speech asset preparation needs network access; recording recognition runs on-device afterward.

## 1. Prepare local transcription

Clone to a durable location. On a supported modern Mac:

```sh
git clone https://github.com/alvarezdaymion/ConcoDispatch.git "$HOME/src/ConcoDispatch"
cd "$HOME/src/ConcoDispatch"
make native
dist/concodispatch-transcribe --check
mkdir -p "$HOME/Library/Application Support/Hermes Voice Kanban/bin"
cp dist/concodispatch-transcribe "$HOME/Library/Application Support/Hermes Voice Kanban/bin/transcribe"
"$HOME/Library/Application Support/Hermes Voice Kanban/bin/transcribe" --prepare
```

`--check` queries support/assets without downloading. `--prepare` is the explicit setup download. `--locale en-US` is the default; choose a supported locale deliberately. Normal positional audio-file processing never prepares missing assets. Unsupported hardware, missing assets or failed/empty recognition remain recoverable errors.

For an older Mac or explicit Whisper preference, create a venv, install `requirements-audio.txt`, provision `base.en` once with `local_files_only=False`, then configure `VOICE_KANBAN_STT_BACKEND=whisper` and that venv's absolute Python path. Runtime uses `local_files_only=True`.

## 2. Configure routing and state

```sh
mkdir -p "$HOME/Library/Application Support/Hermes Voice Kanban"
cp config.example.sh "$HOME/Library/Application Support/Hermes Voice Kanban/config.sh"
chmod 600 "$HOME/Library/Application Support/Hermes Voice Kanban/config.sh"
```

Edit executable paths to match `command -v python3` and `command -v hermes`. Keep the config private: it is trusted shell code. Do not overwrite an existing deployment's config, receipts or recordings with example defaults.

| Setting | Meaning |
| --- | --- |
| `VOICE_KANBAN_PYTHON` | Absolute receiver Python; only the Whisper backend needs its audio dependencies |
| `VOICE_KANBAN_HERMES_BIN` | Absolute native Hermes CLI path; otherwise PATH/home fallback |
| `VOICE_KANBAN_STT_BACKEND` | Explicit `apple` or `whisper`; old configs without it retain Whisper |
| `VOICE_KANBAN_NATIVE_BIN`, `VOICE_KANBAN_LOCALE` | Compiled Apple helper path and supported speech locale |
| `VOICE_KANBAN_STT_TIMEOUT`, `VOICE_KANBAN_CLI_TIMEOUT` | Positive finite deadlines in seconds; defaults 600 and 30 |
| `VOICE_KANBAN_PROFILE`, `VOICE_KANBAN_BOARD`, `VOICE_KANBAN_ASSIGNEE` | Pin the Hermes home/profile, board and worker; example uses `default` |
| `VOICE_KANBAN_QUEUE_DIR` | Matching Mac iCloud Drive/Shortcuts inbox |
| `VOICE_KANBAN_STATE_DIR` | Existing local archive/receipt directory; keep it stable |
| `VOICE_KANBAN_ENVELOPE_MARKER` | Legacy text marker, default `VOICEKANBAN/2` |
| `VOICE_KANBAN_NOTIFY_TARGET` | Optional message destination; empty disables sends |
| `VOICE_KANBAN_CONFIG` | Optional alternate shell config path |

New receipts preserve their routing across retries. Historical receipts have no routing evidence: keep their original board/profile configuration during the first upgraded pass, especially after an uncertain create. Do not switch an old deployment's board while work is pending. Old configs omitting board/profile retain their legacy ambient routing; set explicit values for new deployments.

## 3. Build/import capture Shortcuts

```sh
python3 -m voice_kanban.build_shortcut --platform mobile
python3 -m voice_kanban.build_shortcut --platform mac-audio
shortcuts sign --mode anyone --input 'dist/ConcoDispatch.unsigned.shortcut' --output 'dist/ConcoDispatch.shortcut'
open 'dist/ConcoDispatch.shortcut'
```

Sign/import `ConcoDispatch Mac.unsigned.shortcut` similarly for the new Mac audio path. Launch it from Shortcuts or bind a native Shortcut keyboard/menu-bar gesture. It uses the same iCloud queue rather than the legacy direct-Triage path.

Create `VoiceKanbanInbox/` under iCloud Drive/Shortcuts in Files. To preserve another queue, pass `--queue-folder 'ExistingInbox/'` and use its matching Mac config path. Record Audio must start **Immediately** and finish **On Tap**. Stop queues the recording automatically; no file picker, review or separate Send step.

On the phone, select the Shortcut under Settings → Action Button → Shortcut, or use another existing launch gesture. Run manually once for permissions. On upgrades, preserve the existing Shortcut identity/button binding; importing a same-named duplicate is not a guaranteed update. Never edit Apple's Shortcuts database directly.

## 4. Start the launchd receiver

Generate a definition only; this command does not load a service:

```sh
python3 -m voice_kanban.build_launchagent --runtime "$PWD"
plutil -lint dist/io.concodispatch.receiver.plist
```

For a reviewed live revision, create the configured state directory before loading (launchd needs its log paths), copy the plist into `~/Library/LaunchAgents/`, then explicitly load it with `launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/io.concodispatch.receiver.plist"`. Use `launchctl print "gui/$(id -u)/io.concodispatch.receiver"` to inspect it and `launchctl bootout "gui/$(id -u)/io.concodispatch.receiver"` before replacing it. Keep config paths aligned; `--config`, `--state`, `--interval` and `--runtime` are generator options.

Use `scripts/install_snapshot.py` to produce a commit-frozen runtime when deploying reviewed source, and point the generated service at that path. The compiled speech helper and private config stay outside the snapshot. Do not change source beneath an active receiver.

**Migration:** remove the old queue-capable Hammerspoon module from active use or reload the updated trigger-only version before starting launchd. The advisory lock is defensive protection, not a reason to keep two schedulers. Do not discard existing state. The optional legacy hold-backslash module still launches `Hermes Voice Kanban Mac`; rebuild that preserved Triage Shortcut with `--platform mac` only if needed.

`/bin/sh scripts/consume.sh` performs one configured pass and can create real tasks. `python3 -m voice_kanban.consumer` reads exported environment variables rather than sourcing shell config. Tests must never point either at a live queue.

## Delivery, recovery and testing

A saved notification means **queued**, not delivered or executed. iCloud sync, receiver scheduling, transcription and the gateway's dispatcher add delay. Card confirmation is not worker-start proof. A sleeping Mac cannot receive, and transcription can be imperfect.

The receiver archives before recognition, pins the complete transcript, reads the native task back exactly, and safely removes only the unchanged source. Failures preserve recoverable audio and reuse the original key. Optional messages run after intake/cleanup with deadlines; they can still duplicate after uncertain send responses. Archives have no automatic purge.

```sh
make check
```

Canonical tests are isolated, synthetic and standard-library-only. Native compile/error-path tests run when a compatible Mac SDK is available; they do not download assets. Use real synthetic audio and an isolated Hermes home/board for opt-in integration. Real microphone capture, Shortcut editor rendering/import, iCloud, locked-phone launch and actual worker execution remain separate acceptance gates.

To synthesize a long narration with a six-second thinking pause, run `NATIVE_SPEECH_PROOF=1 python3 -m unittest discover -s tests -p test_native_speech.py -v` after explicitly preparing speech assets. This requires the local `say` voice and ffmpeg; it never records a microphone. Then run the real-CLI replay check:

```sh
python3 scripts/test_audio_integration.py \
  --audio .local/native-proof/narration.m4a \
  --native-bin dist/concodispatch-transcribe \
  --hermes-bin "$(command -v hermes)" \
  --expect 'Purple lantern opens this recording' \
  --expect 'after a quiet pause' \
  --expect 'Silver compass closes this recording'
```

The harness pins isolated `HOME`, `HERMES_HOME`, `HERMES_KANBAN_HOME` and `HERMES_KANBAN_DB`, checks the exact task body, then replays without a recognizer and verifies one task. It does not start a gateway or prove worker execution. Prepare the final compiled helper path explicitly if its `--check` reports missing assets.

See [design/recovery](docs/design.md), [phone acceptance](docs/phone-tests.md) and [security](SECURITY.md). Never repeat an important request blindly or reset receipts to force delivery.
