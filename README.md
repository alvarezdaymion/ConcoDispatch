# ConcoDispatch

**Hold a phone button. Explain the task. Tap Stop to queue it for an agent.**

A small iPhone-to-Mac bridge for [Hermes Agent Kanban](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban). It keeps task capture simple while preserving the context in a long spoken explanation.

```text
iPhone Action Button → Record Audio → Stop → iCloud queue
                                                ↓
Mac: archive audio → local transcription → full task body → Hermes Kanban
```

The Mac also supports a hold-backslash dictation shortcut that creates a Triage card directly.

## Why audio first?

The original workflow used Apple's **Dictate Text** action. Even with Stop Listening set to **On Tap**, live dictation can end before the speaker is finished. Audio-first capture separates recording from recognition: the operator decides when to stop, then the Mac transcribes the saved file.

No file picker, transcript review, or separate Send step. No silence-based submission. No cloud transcription credential or per-minute API bill. Recordings are handled by Apple's iCloud handoff, then archived and transcribed locally on the Mac.

## Included

- Rebuildable mobile Shortcut: immediate recording, manual Stop, unique capture filename, literal iCloud folder.
- An alternative mobile dictation workflow, rebuildable using `--capture-mode dictation`.
- Python receiver: local archival, SQLite receipts, stable Hermes idempotency keys, legacy text support.
- Local English transcription using `faster-whisper` and a provisioned `base.en` model. Normal processing does not download a model or fall back to a cloud provider.
- Mac Shortcut source and Hammerspoon hold-backslash trigger, with phone-queue polling every 15 seconds.
- Synthetic regression tests and CI on Linux and macOS.

Generated Shortcuts, recordings, receipts, private settings, and account-bound exports are excluded from Git.

## Requirements

- An iPhone with Shortcuts and a supported Action Button, or another existing Shortcut launch gesture.
- The same Apple account, with iCloud Drive and Shortcuts sync enabled on the phone and Mac.
- A Mac that stays awake, logged in, and online while receiving tasks.
- Hammerspoon with the necessary macOS accessibility permissions.
- Hermes Agent with Kanban, its gateway dispatcher, and a configured `default` profile. Mobile captures route to `default`; the preserved Mac path creates Triage cards.
- Python 3.9+ for source generation/tests; Python 3.12 recommended for the optional transcription environment.

Microphone permissions, locked-phone launch, synchronization, and long recording behavior must be checked on each physical phone. A generated Shortcut is not proof of those conditions.

## 1. Set up local transcription

Clone to a durable location:

```sh
git clone https://github.com/alvarezdaymion/ConcoDispatch.git "$HOME/src/ConcoDispatch"
cd "$HOME/src/ConcoDispatch"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-audio.txt
```

Provision the model once, deliberately allowing its public download during setup:

```sh
.venv/bin/python -c 'from faster_whisper import WhisperModel; WhisperModel("base.en", device="cpu", compute_type="int8", local_files_only=False)'
```

Normal processing uses `local_files_only=True`. A missing dependency/model is a recoverable error, not permission to upload a recording elsewhere.

## 2. Configure the queue

Create the receiver config:

```sh
mkdir -p "$HOME/Library/Application Support/Hermes Voice Kanban"
cp config.example.sh "$HOME/Library/Application Support/Hermes Voice Kanban/config.sh"
chmod 600 "$HOME/Library/Application Support/Hermes Voice Kanban/config.sh"
```

Edit the paths to match your checkout and environment. This file is trusted shell code; keep it private. Configuration and state paths retain the `Hermes Voice Kanban` name for compatibility.

| Setting | Meaning |
| --- | --- |
| `VOICE_KANBAN_PYTHON` | Absolute path to the transcription environment's Python |
| `VOICE_KANBAN_QUEUE_DIR` | Mac's iCloud Drive/Shortcuts queue path |
| `VOICE_KANBAN_STATE_DIR` | Local audio archive and SQLite receipt directory |
| `VOICE_KANBAN_ENVELOPE_MARKER` | Marker for legacy text captures; default `VOICEKANBAN/2` |
| `VOICE_KANBAN_HERMES_BIN` | Optional explicit CLI path; otherwise PATH or the standard home install |
| `VOICE_KANBAN_NOTIFY_TARGET` | Optional receipt destination; empty disables sends |
| `VOICE_KANBAN_CONFIG` | Optional alternate shell config path |

Preserve an existing deployment's queue, state directory, marker, and idempotency records. Do not reset its ledger to install an update.

## 3. Build and import the mobile Shortcut

```sh
python3 -m voice_kanban.build_shortcut --platform mobile
shortcuts sign --mode anyone \
  --input 'dist/ConcoDispatch.unsigned.shortcut' \
  --output 'dist/ConcoDispatch.shortcut'
open 'dist/ConcoDispatch.shortcut'
```

The default folder is `VoiceKanbanInbox/` relative to iCloud Drive/Shortcuts. Create that folder in Files. To preserve an existing folder, pass `--queue-folder 'ExistingInbox/'` and set the matching Mac path in the receiver config.

For a new installation, select the imported Shortcut under Settings → Action Button → Shortcut. For an update, preserve the existing Shortcut identity: a same-named import may create a duplicate rather than update a phone's button reference. Update its existing action chain through Shortcuts if needed. Never edit Apple's Shortcuts database directly.

The first action must render as **Record Audio**, **Start Recording: Immediately**, **Finish Recording: On Tap**. Stop submits automatically. Run manually once to approve permissions, then test the normal button flow.

## 4. Start the receiver

`/bin/sh scripts/consume.sh` performs one configured import pass. It can create real tasks; do not point a test configuration at a real queue. `python3 -m voice_kanban.consumer` reads exported environment variables rather than sourcing the shell config.

For polling and the preserved Mac trigger, load the module once from `~/.hammerspoon/init.lua`, preserving unrelated configuration:

```lua
require("hs.ipc")
local repo = os.getenv("HOME") .. "/src/ConcoDispatch"
voiceKanban = dofile(repo .. "/hammerspoon/voice_kanban.lua").start({
    repo = repo,
    shortcutName = "Hermes Voice Kanban Mac",
})
```

Reload Hammerspoon. It runs an immediate queue pass and checks every 15 seconds, without overlapping its own passes. Use a reviewed, frozen source revision for live validation; do not change source beneath an active receiver.

Rebuild the unchanged Mac Shortcut with `--platform mac`, then sign/import it as above. A normal backslash tap stays a typed backslash; holding starts Mac dictation; tapping again presses Stop.

## Delivery and recovery

The phone's saved notification means **queued**, not delivered. iCloud has variable sync latency. The Mac must be awake and online with Hammerspoon and the Hermes gateway running.

The receiver archives audio before transcription or task creation. Full audio transcripts go into the task body, with a short board title. Failures retain the source and archive for retry; original recordings remain locally archived without an automatic purge. Replays reuse the capture identity rather than intentionally launching duplicate work.

Do not immediately repeat an important request because a card has not appeared. First inspect the queue, receipt, archive, and error to distinguish sync delay from processing failure. See [design and recovery](docs/design.md) and the [physical-phone acceptance checklist](docs/phone-tests.md).

## Tests and limits

```sh
make check
```

The standard-library suite uses synthetic fixtures and mocked subprocesses. It does not contact a live board, record a microphone, or validate iCloud. Use synthetic audio and an isolated Hermes board for local end-to-end checks. Physical phone tests are a separate final gate.

This is not a guaranteed delivery service. A sleeping Mac cannot receive; iCloud can delay; local transcription is imperfect. English `base.en` is the initial model. The unchanged Mac dictation path still has its original timeout and weaker recovery properties. Optional receipt sends can duplicate after an uncertain response, and contain a short transcript summary; enable them deliberately.

## Portfolio and demonstration

The project demonstrates a minimal interface backed by durable automation, not guaranteed iCloud delivery. Use synthetic recordings and isolated boards; never expose real task content or account identifiers. See [security guidance](SECURITY.md) for data handling and vulnerability reporting.
