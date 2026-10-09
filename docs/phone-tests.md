# Phone acceptance test

The interaction remains: hold the existing Action Button, speak, tap Stop. No separate Send step.

Run these on every participating phone after its Shortcut has synced:

1. Open the Shortcut editor. Its first action must be **Record Audio**, with **Start Recording: Immediately** and **Finish Recording: On Tap**. If it still says Dictate Text, the old copy is still present on that phone.
2. Short capture: state a harmless, identifiable test request and tap Stop. Confirm one Kanban card arrives and contains the full transcript in its body.
3. Long capture: speak for several minutes. Include a recognizable opening phrase and a different final phrase. Take a thinking pause in the middle. It must remain recording until Stop, and both phrases must appear in the task body.
4. If multiple phones are used, repeat the normal Action Button flow on each. Confirm each distinct recording produces one card, not two.
5. Check the locked-phone launch separately; microphone permissions and locked-device behavior are physical-device checks, not guaranteed by source generation or Mac import.

Use harmless requests, for example asking the agent to acknowledge the test and take no external action. Real captures still launch real agents automatically.

The phone's saved notification means **queued**, not received or executed. iCloud sync has variable latency. The Mac must be awake and online; Hammerspoon and the Hermes gateway must be running. Local audio transcription adds processing time after Stop.

If nothing arrives, do not repeat a real request immediately: first inspect the phone's saved notification, iCloud queue, receiver error, and SQLite receipt to distinguish sync delay from processing failure. Audio remains in the local archive for retry. Retrying with the same capture identity must not create a second card.

Rollback: rebuild/import the mobile Shortcut with `--capture-mode dictation`, keeping the same queue folder. The audio-capable receiver accepts legacy text captures, so rolling back the capture UI does not require discarding the receipt ledger or reverting the receiver.
