-- Used by the generated Mac Shortcut; input is the Dictated Text action output.
on run {input, parameters}
    set capturedText to ""
    try
        set capturedText to input as text
    end try

    if capturedText is "" then
        display notification "Nothing was captured; no card was created." with title "Hermes Voice Kanban"
        return "empty capture"
    end if

    set homePath to POSIX path of (path to home folder)
    set configPath to homePath & "Library/Application Support/Hermes Voice Kanban/config.sh"
    set resolveCommand to "if [ -f " & quoted form of configPath & " ]; then . " & quoted form of configPath & "; fi; if [ -n \"${VOICE_KANBAN_HERMES_BIN:-}\" ]; then printf '%s' \"$VOICE_KANBAN_HERMES_BIN\"; elif command -v hermes >/dev/null 2>&1; then command -v hermes; else printf '%s' \"$HOME/.hermes/hermes-agent/venv/bin/hermes\"; fi"

    try
        set hermesPath to do shell script resolveCommand
        set commandText to quoted form of hermesPath & " kanban create --triage --created-by mac-voice-capture --json " & quoted form of capturedText
        set commandOutput to do shell script commandText
        display notification "Added to the Triage column." with title "Hermes Voice Kanban"
        return commandOutput
    on error errorMessage number errorNumber
        display notification "Capture failed. Open Shortcuts for the error." with title "Hermes Voice Kanban"
        error errorMessage number errorNumber
    end try
end run
