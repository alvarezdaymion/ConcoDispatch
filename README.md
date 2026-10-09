# Hermes Voice Kanban

Turn a spoken note into a Hermes Kanban card using Apple Shortcuts, iCloud Drive, and a small standard-library Python consumer.

**iPhone:** hold the Action Button → dictate → tap **Stop** → save a text capture to iCloud → the awake Mac imports it into Kanban. The phone says **queued**, not delivered.

**Mac:** hold `\` for 0.35 seconds → dictate → tap `\` again (or click **Stop**) → create a Triage card directly. A short tap still types `\` normally. Releasing the initial hold does not stop dictation.

This repository preserves a working dictation-based design, including its limitations. It does **not** record audio or add a separate transcription service.

## Requirements

- iPhone with Shortcuts and an Action Button (or launch the mobile Shortcut manually).
- Mac with Shortcuts, Python 3.9+, and [Hammerspoon](https://www.hammerspoon.org/). Grant Hammerspoon Accessibility permission; grant Shortcuts microphone/speech permissions and allow running scripts on Mac.
- The same Apple account with **iCloud Drive and Shortcuts sync enabled** on both devices. Keep the queue downloaded on the Mac. The Mac must be awake, logged in, and running Hammerspoon for polling.
- [Hermes Agent](https://hermes-agent.nousresearch.com/docs/) installed with Kanban available and a configured **default** profile. For automatic card execution, the Hermes gateway/Kanban dispatcher must be running. Mobile cards are assigned to `default`; Mac cards enter Triage and follow your board's routing policy.
- A Hermes CLI supporting `kanban create --assignee`, `--triage`, `--created-by`, `--idempotency-key`, and `--json`. Check `hermes kanban create --help` before installing. Optional notifications also require a configured `hermes send --to` destination.

No Python dependencies or service credentials are required by this package. Hermes itself needs its normal configuration.

## 1. Rebuild and import the Shortcuts

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
make shortcuts
```

This generates unsigned binary plists under ignored `dist/`. The builder is the source of truth; no signed Shortcuts or account-bound export metadata belong in Git.

On Mac, sign the generated files locally before importing them:

```sh
shortcuts sign --mode anyone \
  --input "dist/Hermes Voice Kanban Mobile.unsigned.shortcut" \
  --output "dist/Hermes Voice Kanban Mobile.shortcut"
shortcuts sign --mode anyone \
  --input "dist/Hermes Voice Kanban Mac.unsigned.shortcut" \
  --output "dist/Hermes Voice Kanban Mac.shortcut"
open "dist/Hermes Voice Kanban Mobile.shortcut"
open "dist/Hermes Voice Kanban Mac.shortcut"
```

Signing requires Apple's local Shortcuts signing support and may require network access. These commands only prepare artifacts; review the actions in Shortcuts before running them. Name the imported workflows **Hermes Voice Kanban Mobile** and **Hermes Voice Kanban Mac**. If macOS won't import a rebuilt workflow, create its actions manually using [the source map](docs/design.md#shortcut-source-map).

In Files, create **iCloud Drive → Shortcuts → VoiceKanbanInbox**. Verify the mobile **Save File** action points to that folder, has **Ask Where to Save off**, and **Overwrite off**. Let the mobile Shortcut sync to iPhone, then select it in **Settings → Action Button → Shortcut**. Run it manually once to approve permissions.

## 2. Configure the Mac consumer

Keep this checkout in a stable location. For the examples below, use `~/src/hermes-voice-kanban`, or change the local `repo` setting in the next step.

```sh
mkdir -p "$HOME/Library/Application Support/Hermes Voice Kanban"
cp config.example.sh "$HOME/Library/Application Support/Hermes Voice Kanban/config.sh"
```

Edit that private file if needed. Set an absolute `VOICE_KANBAN_HERMES_BIN` when GUI applications cannot find Hermes on `PATH`. Use `command -v hermes` in your terminal to locate it. The Mac AppleScript and queue launcher both read this default config file. It is trusted shell code, not a dotenv parser.

| Variable | Default / meaning |
| --- | --- |
| `VOICE_KANBAN_HERMES_BIN` | `hermes` found on `PATH`, otherwise `~/.hermes/hermes-agent/venv/bin/hermes` |
| `VOICE_KANBAN_QUEUE_DIR` | Mac path for iCloud Drive/Shortcuts/VoiceKanbanInbox (`~/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/VoiceKanbanInbox`) |
| `VOICE_KANBAN_STATE_DIR` | `~/Library/Application Support/Hermes Voice Kanban` (archive and SQLite receipts) |
| `VOICE_KANBAN_ENVELOPE_MARKER` | `VOICEKANBAN/2`; must match the mobile build |
| `VOICE_KANBAN_NOTIFY_TARGET` | Empty; no outbound receipts unless explicitly configured |
| `VOICE_KANBAN_PYTHON` | `python3`, used by the shell launcher |
| `VOICE_KANBAN_CONFIG` | Optional alternate config file for the shell launcher only |

The builder accepts `--queue-folder` (relative to iCloud Drive/Shortcuts) and `--envelope-marker`. For example:

```sh
python3 -m voice_kanban.build_shortcut --platform mobile \
  --queue-folder 'LocalInbox/' --envelope-marker 'LOCALVOICE/2'
```

Set the consumer's absolute queue path and marker to match. Changing a marker on a nonempty queue can turn an envelope into legacy plain text; drain the old queue first or preserve its existing marker locally. Do not change the receipt state directory casually: it carries deduplication history.

`/bin/sh scripts/consume.sh` performs **one real import pass** using the config file. `python3 -m voice_kanban.consumer` also performs one pass, but reads only exported environment variables. Do not run either against a real queue as a syntax check.

## 3. Enable the hotkey and polling

Add this to your existing `~/.hammerspoon/init.lua` without replacing unrelated configuration:

```lua
local repo = os.getenv("HOME") .. "/src/hermes-voice-kanban"
voiceKanban = dofile(repo .. "/hammerspoon/voice_kanban.lua").start({
    repo = repo,
    shortcutName = "Hermes Voice Kanban Mac",
})
```

Reload Hammerspoon once. This enables login autostart, the hold-backslash hotkey, one immediate queue pass, and polling every **15 seconds**. It does not launch overlapping queue consumers within that Hammerspoon instance. Do not enable a second poller or manually import concurrently. Optional settings: `holdSeconds`, `queueIntervalSeconds`, and `shortcutsCLI`.

## Check the installed flow

1. Dictate a harmless synthetic note on iPhone and tap Stop. Verify the queued notification and the named `.txt` file, if it hasn't already been consumed.
2. With the Mac awake, wait for iCloud sync and a polling pass. Verify the exact card on your Hermes board; then verify the source file disappeared and its archive exists under the state directory.
3. Test a short `\` tap, hold-to-dictate, and second-tap-to-stop on Mac. Verify its card is in Triage. If the accessibility Stop lookup fails, click Stop yourself.
4. Only if you enabled a notification target, verify its receipt separately. A local Shortcut notification does not prove delivery or task execution.

Tests use synthetic files and a fake Hermes executable; they never call your gateway or touch your board. CI rebuilds both workflows and compiles AppleScript on Mac, but cannot prove phone permissions, actual dictation, iCloud sync, or GUI accessibility behavior.

## Known limitations

- **Apple Dictate Text can time out during longer notes even with “On Tap.”** There is no audio backup. Keep captures short and verify important notes; long-form reliability is not fixed in this baseline.
- iCloud is asynchronous. Fifteen-second polling is not a delivery SLA; a sleeping Mac does not consume the queue.
- Mac capture creates a Triage card directly and has no durable mobile queue or replay key. The two paths intentionally have different routing and recovery behavior.
- Stop-button lookup uses English accessibility labels. Other languages or changed Apple UI may require manual Stop.
- Retry safety relies on Hermes honoring the idempotency key. Notification retries can duplicate a receipt if a send succeeded but its response was lost. There is no subprocess timeout or cross-process consumer lock.
- Queue files, archives, and receipts contain private text. Keep them out of Git and restrict access. Optional receipts send a short transcript summary to your configured destination.

See [design and recovery behavior](docs/design.md) for the envelope, receipt state, and retained failure cases.
