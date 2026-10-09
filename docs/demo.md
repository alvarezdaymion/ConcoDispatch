# Demonstration notes

## The project in one sentence

A physical phone button turns a spoken explanation into an actionable agent task, without making the operator use a task-management interface.

## Story spine

1. Show the interaction: launch the Shortcut, speak naturally, tap Stop, then show the resulting task after delivery.
2. Explain why you'd use it: give your agent a task while away from your desk, without typing or copying a voice note into chat.
3. Show that you can explain the full thought and pause to think. Recording ends when you tap Stop.
4. Show the result: Hermes receives the full transcript and its configured worker starts the task.
5. Demonstrate a long explanation with a thinking pause and a clearly spoken final instruction. Show that the final instruction reaches the card and the agent.
6. Explain the honest limits: variable iCloud sync, an awake Mac, physical-device permissions, and imperfect transcription.

## Evidence to capture before publishing

- Each participating phone launching its Shortcut from the button.
- A recording continuing for several minutes and through a thinking pause.
- Stop automatically submitting without a file picker or extra Send step.
- The exact task body containing the opening and final phrases.
- The agent starting from the resulting card.
- A replay producing no duplicate card.
- Source rebuild and passing tests, clearly separated from physical-phone proof.

Use a dedicated synthetic task and recording. Avoid real boards, personal task titles, account/device identifiers, contacts, local paths, recordings, and receipt destinations on screen. Blur interface identifiers before publishing if a clean demo environment cannot be used.

## A clean demo sequence

1. Show only the phone's ConcoDispatch recording interface, with notifications and personal UI hidden. Use a harmless request to acknowledge a demonstration, not a business action.
2. Say a distinct opening phrase, explain the test naturally, pause deliberately, then say a distinct closing phrase and tap Stop. For a long-form claim, record the full several-minute take; a cut around the pause is not proof of continuity.
3. Show the queued notification without presenting it as delivery confirmation. If the edit skips sync/processing time, label the cut rather than implying instantaneous dispatch.
4. Show only the demonstration card's complete body and actual worker result. Crop other tasks, account names, IDs and machine paths. Confirm the final transcript sentence with the speaker.
5. Keep raw evidence privately. Publish only the sanitized clip. Describe synthetic local transcription tests, actual phone capture and clean-install checks as different proof layers.

Before sharing the source, verify the delivered commit's tests, setup instructions, history/metadata privacy, license and prerequisites. A successful installation on an already configured Mac is not proof of a brand-new Apple account or a fresh operating-system permission state.

This is a demonstration checklist, not evidence that physical-phone acceptance tests have passed.
