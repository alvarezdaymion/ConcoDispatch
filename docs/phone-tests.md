# Phone acceptance test

Launch ConcoDispatch, speak, and tap Stop. No separate Send step. Use the Action Button if your phone has one, or another Shortcut launch option.

Run these on every participating phone after its Shortcut has synced:

1. Open the Shortcut editor. Its first action must be **Record Audio**, with **Start Recording: Immediately** and **Finish Recording: On Tap**. If it still says Dictate Text, the old copy is still present on that phone.
2. Short capture: state a harmless, identifiable test request and tap Stop. Confirm one Kanban card arrives and contains the full transcript in its body.
3. Long capture: speak for several minutes. Include a recognizable opening phrase and a different final phrase. Take a thinking pause in the middle. It must remain recording until Stop, and both phrases must appear in the task body.
4. If multiple phones are used, repeat the normal Action Button flow on each. Confirm each distinct recording produces one card, not two.
5. Check the locked-phone launch separately; microphone permissions and locked-device behavior are physical-device checks, not guaranteed by source generation or Mac import.

Use harmless requests, for example asking the agent to acknowledge the test and take no external action. Real captures still launch real agents automatically.

The phone's saved notification means **queued**, not received or executed. iCloud sync has variable latency. The Mac must be awake and online; the launchd receiver and Hermes gateway must be running. Hammerspoon is not required. Local audio transcription and gateway dispatch add processing time after Stop.

If nothing arrives, do not repeat a real request immediately: first inspect the phone's saved notification, iCloud queue, receiver error, and SQLite receipt to distinguish sync delay from processing failure. Audio remains in the local archive for retry. Retrying with the same capture identity must not create a second card.

For an existing installation that needs the older text workflow, see [manual setup](manual-setup.md). Preserve the Shortcut's identity and button binding when changing its actions; importing a same-named copy is not a safe in-place update. The receiver accepts legacy text captures without discarding the existing receipt ledger.
