# Copy to ~/Library/Application Support/Hermes Voice Kanban/config.sh.
# This is sourced shell code: keep it private and only use trusted contents.
# Leave Hermes unset to resolve it from PATH, then the standard home install.
# export VOICE_KANBAN_HERMES_BIN="$HOME/.hermes/hermes-agent/venv/bin/hermes"
export VOICE_KANBAN_PYTHON="$HOME/src/ConcoDispatch/.venv/bin/python"
export VOICE_KANBAN_QUEUE_DIR="$HOME/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/VoiceKanbanInbox"
export VOICE_KANBAN_STATE_DIR="$HOME/Library/Application Support/Hermes Voice Kanban"
export VOICE_KANBAN_ENVELOPE_MARKER="VOICEKANBAN/2"
# Optional: configure a Hermes send --to target locally. Empty means no sends.
export VOICE_KANBAN_NOTIFY_TARGET=""
