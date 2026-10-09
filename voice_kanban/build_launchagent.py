"""Generate a per-user receiver LaunchAgent without loading or installing it."""
from __future__ import annotations

import argparse
from pathlib import Path
import plistlib

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = Path.home() / 'Library/Application Support/Hermes Voice Kanban'
LABEL = 'io.concodispatch.receiver'


def build_launchagent(runtime: Path, *, config: Path = DEFAULT_STATE / 'config.sh',
                      state: Path = DEFAULT_STATE, interval: int = 15,
                      app: Path | None = None) -> dict:
    runtime = runtime.expanduser().resolve()
    config, state = config.expanduser().absolute(), state.expanduser().absolute()
    if interval < 1:
        raise ValueError('Polling interval must be positive')
    if not (runtime / 'scripts/consume.sh').is_file():
        raise ValueError('Runtime must contain scripts/consume.sh')
    arguments = ['/bin/sh', str(runtime / 'scripts/consume.sh')]
    if app is not None:
        arguments = ['/usr/bin/open', '-W', '-g', '-a', str(app.expanduser().absolute()),
                     '--args', '--runtime', str(runtime), '--config', str(config),
                     '--state', str(state)]
    return {
        'Label': LABEL,
        'ProgramArguments': arguments,
        'WorkingDirectory': str(runtime),
        'EnvironmentVariables': {
            'VOICE_KANBAN_CONFIG': str(config),
            'VOICE_KANBAN_STATE_DIR': str(state),
            'PATH': '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin',
        },
        'RunAtLoad': True,
        'StartInterval': interval,
        'StandardOutPath': str(state / 'receiver.log'),
        'StandardErrorPath': str(state / 'receiver-error.log'),
        'Umask': 0o077,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=ROOT)
    parser.add_argument('--app', type=Path, help='Dedicated native receiver app for macOS privacy grants')
    parser.add_argument('--config', type=Path, default=DEFAULT_STATE / 'config.sh')
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--interval', type=int, default=15)
    parser.add_argument('--output', type=Path, default=Path('dist') / (LABEL + '.plist'))
    args = parser.parse_args()
    definition = build_launchagent(args.runtime, config=args.config, state=args.state,
                                   interval=args.interval, app=args.app)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(plistlib.dumps(definition))
    print(args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
