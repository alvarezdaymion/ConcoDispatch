# Copy to ~/Library/Application Support/Hermes Voice Kanban/config.sh.
# This is sourced shell code: keep it private and only use trusted contents.
# Leave Hermes unset to resolve it from PATH, then the standard home install.
# Pin this to the output of command -v hermes in your installation.
# export VOICE_KANBAN_HERMES_BIN="/absolute/path/to/hermes"
# Apple speech needs only the receiver's standard-library Python.
export VOICE_KANBAN_PYTHON="/usr/bin/python3"
export VOICE_KANBAN_STT_BACKEND="apple"
export VOICE_KANBAN_NATIVE_BIN="$HOME/Library/Application Support/Hermes Voice Kanban/bin/transcribe"
export VOICE_KANBAN_LOCALE="en-US"
export VOICE_KANBAN_STT_TIMEOUT="600"
export VOICE_KANBAN_CLI_TIMEOUT="30"
export VOICE_KANBAN_PROFILE="default"
export VOICE_KANBAN_BOARD="default"
export VOICE_KANBAN_ASSIGNEE="default"
export VOICE_KANBAN_QUEUE_DIR="$HOME/Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents/VoiceKanbanInbox"
export VOICE_KANBAN_STATE_DIR="$HOME/Library/Application Support/Hermes Voice Kanban"
export VOICE_KANBAN_ENVELOPE_MARKER="VOICEKANBAN/2"
# Optional: configure a Hermes send --to target locally. Empty means no sends.
export VOICE_KANBAN_NOTIFY_TARGET=""
