# Demonstration notes

## The project in one sentence

A physical phone button turns a spoken explanation into an actionable agent task, without making the operator use a task-management interface.

## Story spine

1. Show the existing interaction: hold the button, speak naturally, tap Stop, task appears.
2. Explain the failure: live dictation can end while the person is still giving context.
3. Show the minimal fix: capture audio first, then transcribe locally. The interaction stays the same.
4. Reveal the necessary reliability behind the simple interface: unique capture identity, local audio archive, persistent receipts, retry-safe creation, and full context in the task body.
5. Demonstrate a long explanation with a thinking pause and a clearly spoken final instruction. Show that the final instruction reaches the card and the agent.
6. Explain the honest limits: variable iCloud sync, an awake Mac, physical-device permissions, and imperfect transcription.

## Evidence to capture before publishing

- Both phones launching their existing Shortcut from the button.
- A recording continuing beyond the previously observed cutoff and through a thinking pause.
- Stop automatically submitting without a file picker or extra Send step.
- The exact task body containing the opening and final phrases.
- The agent starting from the resulting card.
- A replay producing no duplicate card.
- Source rebuild and passing tests, clearly separated from physical-phone proof.

Use a dedicated synthetic task and recording. Avoid real boards, personal task titles, account/device identifiers, contacts, local paths, recordings, and receipt destinations on screen. Blur interface identifiers before publishing if a clean demo environment cannot be used.

The repository remains private until publication is explicitly approved. These notes are a future demonstration outline, not a script, filming assignment, or proof that the physical-phone acceptance tests have passed.
