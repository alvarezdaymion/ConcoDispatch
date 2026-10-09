-- Tap backslash normally; hold to dictate; tap again to press Stop.
-- Optional legacy Mac dictation trigger only; launchd owns audio queue intake.
local M = {}

function M.start(settings)
    settings = settings or {}
    local HOLD_SECONDS = settings.holdSeconds or 0.35
    local SHORTCUT_NAME = settings.shortcutName or "Hermes Voice Kanban Mac"
    local SHORTCUTS_CLI = settings.shortcutsCLI or "/usr/bin/shortcuts"

    local trigger
    local holdTimer
    local holdFired = false
    local captureTask

    local function notifyFailure(message)
        hs.notify.new({title = "Hermes Voice Kanban", informativeText = message}):send()
    end

    local function startVoiceCapture()
        holdFired = true
        if captureTask and captureTask:isRunning() then
            notifyFailure("A voice capture is already running.")
            return
        end
        captureTask = hs.task.new(SHORTCUTS_CLI, function(exitCode, _, stderr)
            if exitCode ~= 0 then
                local detail = (stderr and stderr ~= "") and stderr or "Shortcut exited with an error."
                notifyFailure(detail)
            end
            captureTask = nil
        end, {"run", SHORTCUT_NAME})
        if not captureTask or not captureTask:start() then
            captureTask = nil
            notifyFailure("Could not start the voice-capture shortcut.")
        end
    end

    local STOP_LABELS = {["Stop dictation"] = true, ["Stop Listening"] = true}
    local function axAttribute(element, name)
        local ok, value = pcall(function() return element:attributeValue(name) end)
        if ok then return value end
        return nil
    end

    local function findDictationStopButton()
        local service = hs.application.get("com.apple.WorkflowKit.ShortcutsViewService")
        if not service then return nil end
        local root = hs.axuielement.applicationElement(service)
        local seen = {}
        local function walk(element, depth)
            if depth > 20 or seen[element] then return nil end
            seen[element] = true
            if axAttribute(element, "AXRole") == "AXButton"
                and axAttribute(element, "AXEnabled") ~= false then
                for _, name in ipairs({"AXTitle", "AXDescription", "AXHelp", "AXValue"}) do
                    if STOP_LABELS[axAttribute(element, name)] then return element end
                end
            end
            for _, child in ipairs(axAttribute(element, "AXChildren") or {}) do
                local found = walk(child, depth + 1)
                if found then return found end
            end
            return nil
        end
        return walk(root, 0)
    end

    local function pressDictationStop(attempt)
        local button = findDictationStopButton()
        if button then
            local ok, errorMessage = pcall(function() button:performAction("AXPress") end)
            if not ok then notifyFailure("Could not stop dictation: " .. tostring(errorMessage)) end
            return
        end
        if attempt < 10 and captureTask and captureTask:isRunning() then
            hs.timer.doAfter(0.10, function() pressDictationStop(attempt + 1) end)
            return
        end
        notifyFailure("The dictation Stop button could not be found; tap it on screen.")
    end

    local function finishVoiceCapture()
        if not captureTask or not captureTask:isRunning() then return false end
        pressDictationStop(1)
        return true
    end

    trigger = hs.hotkey.new({}, "\\", function()
        holdFired = false
        if holdTimer then holdTimer:stop() end
        if captureTask and captureTask:isRunning() then
            holdFired = true
            finishVoiceCapture()
            return
        end
        holdTimer = hs.timer.doAfter(HOLD_SECONDS, startVoiceCapture)
    end, function()
        if holdTimer then
            holdTimer:stop()
            holdTimer = nil
        end
        if not holdFired then
            -- Replay a tap without recursively firing this hotkey.
            trigger:disable()
            hs.eventtap.keyStroke({}, "\\", 0)
            hs.timer.doAfter(0.05, function() trigger:enable() end)
        end
    end, function() end)

    trigger:enable()
    M.trigger = trigger
    hs.printf("Optional Mac dictation trigger: tap \\ normally; hold %.2fs to dictate; tap \\ again to finish",
              HOLD_SECONDS)
    return M
end

return M
