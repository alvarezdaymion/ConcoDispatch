#!/bin/sh
# Hammerspoon runs this with /bin/sh, so an executable bit is not required.
set -eu
CONFIG=${VOICE_KANBAN_CONFIG:-"$HOME/Library/Application Support/Hermes Voice Kanban/config.sh"}
if [ -f "$CONFIG" ]; then
    . "$CONFIG"
fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "${VOICE_KANBAN_PYTHON:-python3}" "$ROOT/voice_kanban/consumer.py"
