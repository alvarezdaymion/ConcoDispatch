# Demonstration notes

## The project in one sentence

A physical phone button turns a spoken explanation into an actionable agent task, without making the operator use a task-management interface.

## Story spine

1. Show the interaction: hold the button, speak naturally, tap Stop, then show the resulting task after delivery.
2. Explain the failure: live dictation can end while the person is still giving context.
3. Show the audio-first workflow: record until Stop, save to the queue, then transcribe locally.
4. Reveal the necessary reliability behind the simple interface: unique capture identity, local audio archive, persistent receipts, retry-safe creation, and full context in the task body.
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

This is a demonstration checklist, not evidence that physical-phone acceptance tests have passed.
