# ConcoDispatch

**Speak a task. Let your agent get to work.**

ConcoDispatch turns iPhone voice recordings into tasks for your [Hermes](https://hermes-agent.nousresearch.com/) AI agent. Explain what you need, tap Stop, and let Hermes pick it up.

## Why use it?

Give your agent a task while you're walking, away from your desk, or thinking out loud.

- **Keep the context.** Explain the whole task, not just a quick reminder.
- **Pause to think.** Recording ends when you tap Stop, not when you go quiet.
- **Skip the handoff.** No copying into chat, transcript review, or separate Send button.
- **Use what you already have.** Your iPhone, Mac, Apple account, and Hermes. No separate transcription subscription.

## Install

You'll need:

- An iPhone and a Mac using the same Apple account, with iCloud Drive and Shortcuts sync enabled.
- macOS 26 or later. Setup checks support for your Mac and language.
- Hermes installed and configured to run tasks automatically.

**1. Clone this repo on your Mac.**

```sh
git clone https://github.com/alvarezdaymion/ConcoDispatch.git
cd ConcoDispatch
```

**2. Open your AI coding assistant in that folder and ask:**

> Set up ConcoDispatch so I can speak tasks from my iPhone to Hermes. Follow AGENTS.md and docs/setup.md. Use my existing Hermes setup, preserve existing recordings and Shortcuts, and verify a test task reaches the agent.

**3. Finish the device prompts.**

Accept the permissions, add the Shortcut to your iPhone, and choose how to launch it. Use the Action Button if your phone has one. Record a harmless test request and tap Stop.

Your assistant handles the Mac setup. Apple's permissions and phone controls still need your confirmation. [Detailed setup instructions](docs/setup.md).

## How it works

1. Your iPhone saves the recording through iCloud.
2. Your Mac turns it into text locally and keeps the original audio.
3. Hermes receives the full transcript on its task board. Its automatic task runner picks it up using your existing AI setup.

Keep the Mac awake, logged in, and connected. Delivery isn't instant, and a saved notification doesn't mean the task is finished. Transcription can make mistakes. Recordings are kept until you remove them. Hermes's usual AI costs and approval rules still apply.

## More information

[Manual setup and developer reference](docs/manual-setup.md) · [Troubleshooting and recovery](docs/design.md) · [Phone testing](docs/phone-tests.md) · [Privacy and security](SECURITY.md)

Free and open source under the [MIT license](LICENSE).
