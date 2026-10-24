#!/usr/bin/env python3
"""Prepare ConcoDispatch; activation and native Shortcut import require explicit flags.

Active receivers must be explicitly deactivated before preparation.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from scripts.install_snapshot import git, install_snapshot  # noqa: E402
from voice_kanban.build_launchagent import LABEL, build_launchagent  # noqa: E402
from voice_kanban.build_shortcut import write_unsigned  # noqa: E402

SETTINGS = ('HERMES_BIN', 'PYTHON', 'STT_BACKEND', 'NATIVE_BIN', 'LOCALE',
            'STT_TIMEOUT', 'CLI_TIMEOUT', 'PROFILE', 'BOARD', 'ASSIGNEE',
            'QUEUE_DIR', 'STATE_DIR', 'ENVELOPE_MARKER')


def read_config(path: Path, home: Path) -> dict:
    """Source trusted code, suppress its output, export no ambient credentials."""
    if not path.exists():
        return {}
    script = '. "$1" >/dev/null 2>&1 || exit 1; '
    for key in SETTINGS:
        name = 'VOICE_KANBAN_' + key
        script += ('if [ "${' + name + '+yes}" ]; then /bin/sh -c '
                   + shlex.quote('test "${' + name + '+yes}"') + ' || exit 3; '
                   + 'printf "%s\\0%s\\0" ' + key + ' "$' + name + '"; fi; ')
    result = subprocess.run(['/bin/sh', '-c', script, 'setup-config', str(path)],
                            env={'HOME': str(home), 'PATH': '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin'},
                            capture_output=True, timeout=10)
    if result.returncode == 3:
        raise RuntimeError('Config settings must be exported to the receiver subprocess')
    if result.returncode:
        raise RuntimeError('Trusted config could not be sourced (contents suppressed)')
    parts = result.stdout.decode().split('\0')[:-1]
    return dict(zip(parts[::2], parts[1::2]))


def run(command, home: Path, timeout=60):
    return subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=timeout,
                          env={'HOME': str(home), 'PATH': '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin',
                               'LANG': 'en_US.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'})


def require(command, home: Path, timeout=60) -> str:
    result = run(command, home, timeout)
    if result.returncode:
        raise RuntimeError(Path(command[0]).name + ' prerequisite/action failed (diagnostics suppressed)')
    return result.stdout


def settings(args):
    home = args.home.expanduser().resolve()
    state = home / 'Library/Application Support/Hermes Voice Kanban'
    config = (args.config or state / 'config.sh').expanduser().absolute()
    cloud = home / 'Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents'
    values = dict(STT_BACKEND='apple', PYTHON=sys.executable, NATIVE_BIN=str(state / 'bin/transcribe'),
                  LOCALE='en-US', STT_TIMEOUT='600', CLI_TIMEOUT='30', PROFILE='default', BOARD='default',
                  ASSIGNEE='default', QUEUE_DIR=str(cloud / 'VoiceKanbanInbox'), STATE_DIR=str(state),
                  ENVELOPE_MARKER='VOICEKANBAN/2', HERMES_BIN=str(home / '.local/bin/hermes'))
    existing = read_config(config, home)
    if config.exists():
        values['PYTHON'] = '/usr/bin/python3'
        values['HERMES_BIN'] = (shutil.which('hermes', path='/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin')
                                or str(home / '.hermes/hermes-agent/venv/bin/hermes'))
        if existing.get('STT_BACKEND') != 'apple':
            raise RuntimeError('Existing config must explicitly select Apple transcription; no files changed')
        for key in ('NATIVE_BIN', 'QUEUE_DIR', 'STATE_DIR', 'PROFILE', 'BOARD', 'ASSIGNEE', 'ENVELOPE_MARKER'):
            if not existing.get(key):
                raise RuntimeError('Existing config must explicitly pin ' + key + '; no files changed')
        values.update(existing)
    for key in ('HERMES_BIN', 'PROFILE', 'BOARD', 'ASSIGNEE', 'LOCALE'):
        override = getattr(args, key.lower())
        if override is not None:
            if config.exists() and values[key] != override:
                raise RuntimeError('Refusing to change existing config setting ' + key)
            values[key] = override
    for key, value in values.items():
        if not value or any(c in value for c in '\r\n\0'):
            raise RuntimeError('Invalid config setting ' + key)
    for key in ('PROFILE', 'BOARD', 'ASSIGNEE', 'LOCALE'):
        if values[key].startswith('-') or values[key] != values[key].strip():
            raise RuntimeError('Invalid routing/locale setting ' + key)
    for key in ('STT_TIMEOUT', 'CLI_TIMEOUT'):
        if not 0 < float(values[key]) < 86400:
            raise RuntimeError('Unsupported timeout setting ' + key)
    for key in ('STATE_DIR', 'QUEUE_DIR', 'NATIVE_BIN', 'PYTHON', 'HERMES_BIN'):
        path = Path(values[key])
        if not path.is_absolute() or '..' in path.parts:
            raise RuntimeError('Config paths must be absolute: ' + key)
    queue = Path(values['QUEUE_DIR']).resolve().relative_to(cloud.resolve())
    if not queue.parts:
        raise RuntimeError('Queue must be a subfolder of iCloud Drive/Shortcuts')
    state_path, queue_path = Path(values['STATE_DIR']).resolve(), Path(values['QUEUE_DIR']).resolve()
    if state_path == queue_path or state_path in queue_path.parents or queue_path in state_path.parents:
        raise RuntimeError('Queue and state must not overlap')
    if home != Path.home().resolve():
        for path in (config, Path(values['STATE_DIR']), Path(values['QUEUE_DIR']), Path(values['NATIVE_BIN'])):
            path.resolve().relative_to(home)
    return home, config, cloud, values, queue.as_posix() + '/'


def assets(helper, locale, home):
    if not Path(helper).is_file():
        return False
    data = json.loads(require([helper, '--check', '--locale', locale], home))
    return all(data.get(key) is True for key in ('available', 'locale_supported', 'assets_installed'))


def loaded(home, plist=None):
    if home != Path.home().resolve():
        return False
    result = run(['/bin/launchctl', 'print', 'gui/' + str(os.getuid()) + '/' + LABEL], home)
    if result.returncode not in (0, 113):
        raise RuntimeError('Cannot establish receiver service ownership; refusing mutation')
    if result.returncode == 0 and plist is not None and not any(
            line.strip() == 'path = ' + str(plist) for line in result.stdout.splitlines()):
        raise RuntimeError('Loaded receiver label does not match the prepared plist; refusing activation')
    return result.returncode == 0


def check(home, config, cloud, values):
    results = {'config': config.is_file(),
               'hermes': os.access(values['HERMES_BIN'], os.X_OK),
               'python': os.access(values['PYTHON'], os.X_OK),
               'gateway': False, 'icloud': cloud.is_dir(), 'sdk': False, 'assets': False, 'receiver': False,
               'routing': config.is_file() and all(values.get(k) for k in ('PROFILE', 'BOARD', 'ASSIGNEE'))}
    probes = {
        'receiver': lambda: bool(managed_plist(Path(values['STATE_DIR']) / 'receiver.plist',
                                               Path(values['STATE_DIR']), config, values)),
        'sdk': lambda: int(require(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-version'], home).split('.')[0]) >= 26,
        'assets': lambda: assets(values['NATIVE_BIN'], values['LOCALE'], home),
        'gateway': lambda: bool(re.search(r'(?i)\b(?:gateway(?: service)?(?: is)?|status:)\s*running\b',
            require([values['HERMES_BIN'], '--profile', values['PROFILE'], 'gateway', 'status'], home))),
    }
    for name, probe in probes.items():
        try:
            results[name] = bool(probe())
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            pass
    for name, ready in results.items():
        print(name + ': ' + ('ready' if ready else 'missing/not ready'))
    print('Routing is pinned, not a live board/worker proof; gateway output must report running.')
    return 0 if all(results.values()) else 1


def managed_plist(plist, state, config, values=None):
    """Only this exact native-host shape may be replaced or activated."""
    if not plist.exists():
        return None
    data = plistlib.loads(plist.read_bytes())
    argv = data.get('ProgramArguments', [])
    if len(argv) != 12:
        raise RuntimeError('Unrecognized receiver plist; preserve it and migrate manually')
    app, runtime = Path(argv[4]), Path(argv[7])
    runtime.relative_to(state / 'runtimes')
    app.relative_to(state / 'builds')
    if data != build_launchagent(runtime, config=config, state=state, app=app):
        raise RuntimeError('Unrecognized receiver plist; preserve it and migrate manually')
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    if (info.get('CFBundleIdentifier') != 'io.concodispatch.receiverhost'
            or not (app / 'Contents/MacOS/ConcoDispatchReceiver').is_file()
            or (values is not None and info.get('ConcoDispatchSettings') != values)):
        raise RuntimeError('Prepared receiver does not match the current config; review before activation')
    return runtime, app


def prepare(args, home, config, cloud, values, queue):
    if git(ROOT, 'status', '--porcelain').strip():
        raise RuntimeError('Commit and review all source changes before preparation')
    if loaded(home):
        raise RuntimeError('Receiver is active: explicitly deactivate the exact receiver before --prepare')
    state, helper = Path(values['STATE_DIR']), Path(values['NATIVE_BIN'])
    managed_plist(home / 'Library/LaunchAgents' / (LABEL + '.plist'), state, config)
    plist = state / 'receiver.plist'
    managed_plist(plist, state, config)
    if not cloud.is_dir() or not os.access(values['HERMES_BIN'], os.X_OK):
        raise RuntimeError('Missing iCloud Shortcuts directory or Hermes executable; run --check')
    if not os.access(values['PYTHON'], os.X_OK):
        raise RuntimeError('Configured Python is not executable')
    if int(require(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-version'], home).split('.')[0]) < 26:
        raise RuntimeError('macOS 26 SDK is required')
    commit = git(ROOT, 'rev-parse', 'HEAD').decode().strip()
    build = state / 'builds' / commit
    app = build / 'ConcoDispatch Receiver.app'
    info = {'CFBundleIdentifier': 'io.concodispatch.receiverhost', 'CFBundleExecutable': 'ConcoDispatchReceiver',
            'CFBundleName': 'ConcoDispatch Receiver', 'CFBundlePackageType': 'APPL', 'LSUIElement': True,
            'NSMicrophoneUsageDescription': 'Receive locally queued voice captures.',
            'NSSpeechRecognitionUsageDescription': 'Transcribe locally queued voice captures.',
            'ConcoDispatchCommit': commit, 'ConcoDispatchSettings': values,
            'ConcoDispatchSigningIdentity': args.signing_identity or '-'}
    if build.exists() and (not (app / 'Contents/Info.plist').is_file() or
                           plistlib.loads((app / 'Contents/Info.plist').read_bytes()) != info):
        raise RuntimeError('Existing build has incompatible settings; preserve it and review manually')
    if build.exists() and not all((build / name).is_file() and (build / name).stat().st_size
                                 for name in ('ConcoDispatch.shortcut', 'ConcoDispatch.unsigned.shortcut')):
        raise RuntimeError('Existing build is incomplete; preserve it and review manually')
    # Reject symlinked destinations rather than following them into unrelated files.
    for path in (state, state / 'runtimes', config, helper, plist, build):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise RuntimeError('Symlinked installation paths are unsupported')
    old_umask = os.umask(0o077)
    try:
        runtime = install_snapshot(ROOT, state / 'runtimes')
        build.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.setup-', dir=build.parent) as tmp:
            stage = Path(tmp)
            if not build.exists():
                staged_app = stage / app.name
                executable = staged_app / 'Contents/MacOS/ConcoDispatchReceiver'
                executable.parent.mkdir(parents=True)
                (staged_app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
                source = stage / 'receiver.swift'
                source.write_bytes(git(ROOT, 'show', commit + ':native/receiver.swift'))
                require(['/usr/bin/xcrun', 'swiftc', '-parse-as-library', '-O', '-module-cache-path',
                         stage / 'cache', source, '-o', executable], home, 300)
                source.unlink()
                require(['/usr/bin/codesign', '--force', '--sign', args.signing_identity or '-', staged_app], home)
                require(['/usr/bin/codesign', '--verify', '--strict', staged_app], home)
                unsigned = write_unsigned(stage / 'ConcoDispatch.unsigned.shortcut', queue_folder=queue)
                signed = stage / 'ConcoDispatch.shortcut'
                require(['/usr/bin/shortcuts', 'sign', '--mode', 'anyone', '--input', unsigned, '--output', signed], home, 180)
                if not signed.is_file() or not signed.stat().st_size:
                    raise RuntimeError('Shortcuts signing produced no signed artifact')
            if not helper.exists():
                binary = stage / 'transcribe'
                source = stage / 'transcribe.swift'
                source.write_bytes(git(ROOT, 'show', commit + ':native/transcribe.swift'))
                require(['/usr/bin/xcrun', 'swiftc', '-parse-as-library', '-O', '-module-cache-path',
                         stage / 'cache', source, '-o', binary], home, 300)
                source.unlink()
                helper.parent.mkdir(parents=True, exist_ok=True)
                with binary.open('rb') as source, helper.open('xb') as target:
                    shutil.copyfileobj(source, target)
                helper.chmod(0o700)
            require([helper, '--prepare', '--locale', values['LOCALE']], home, 900)
            if not assets(helper, values['LOCALE'], home):
                raise RuntimeError('Speech assets not ready after explicit preparation')
            if not build.exists():
                shutil.rmtree(stage / 'cache', ignore_errors=True)
                (stage / 'transcribe').unlink(missing_ok=True)
                stage.rename(build)
            require(['/usr/bin/codesign', '--verify', '--strict', app], home)
        if loaded(home):
            raise RuntimeError('Receiver became active; deactivate it before switching the plist')
        if not config.exists():
            config.parent.mkdir(parents=True, exist_ok=True)
            with config.open('x') as output:
                output.write('# Trusted shell configuration; keep private.\n')
                output.writelines('export VOICE_KANBAN_' + k + '=' + shlex.quote(v) + '\n' for k, v in values.items())
        Path(values['QUEUE_DIR']).mkdir(parents=True, exist_ok=True)
        definition = plistlib.dumps(build_launchagent(runtime, config=config, state=state, app=app))
        plist.parent.mkdir(parents=True, exist_ok=True)
        if not plist.exists() or plist.read_bytes() != definition:
            with tempfile.NamedTemporaryFile(dir=plist.parent, delete=False) as output:
                output.write(definition)
                staged_plist = Path(output.name)
            staged_plist.replace(plist)
        print('Prepared; receiver inactive. Shortcut not imported. Use --check before explicit --activate.')
    finally:
        os.umask(old_umask)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ('check', 'prepare', 'activate', 'import-shortcut'):
        modes.add_argument('--' + mode, action='store_true')
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--config', type=Path)
    for flag in ('hermes-bin', 'profile', 'board', 'assignee', 'locale', 'signing-identity'):
        parser.add_argument('--' + flag)
    args = parser.parse_args(argv)
    try:
        home = args.home.expanduser().resolve()
        if sys.platform != 'darwin':
            raise RuntimeError('macOS 26+ is required')
        if (args.activate or args.import_shortcut) and home != Path.home().resolve():
            raise RuntimeError('Activation/import are forbidden with an isolated --home')
        if args.import_shortcut:
            if 'ConcoDispatch' in require(['/usr/bin/shortcuts', 'list'], home).splitlines():
                print('Existing ConcoDispatch preserved; no import')
                return 0
        home, config, cloud, values, queue = settings(args)
        if args.check:
            return check(home, config, cloud, values)
        if args.activate or args.import_shortcut:
            state = Path(values['STATE_DIR'])
            plist = home / 'Library/LaunchAgents' / (LABEL + '.plist')
            prepared_plist = state / 'receiver.plist'
            prepared = managed_plist(prepared_plist, state, config, values)
            if not prepared or not config.is_file():
                raise RuntimeError('Run --prepare first')
            runtime, app = prepared
            require(['/usr/bin/codesign', '--verify', '--strict', app], home)
            if args.import_shortcut:
                signed = app.parent / 'ConcoDispatch.shortcut'
                if not signed.is_file():
                    raise RuntimeError('Prepared signed Shortcut is missing')
                require(['/usr/bin/open', '-a', 'Shortcuts', signed], home)
                print('Native import opened; confirm Add Shortcut, then rerun to verify the name')
                return 0
            if not assets(values['NATIVE_BIN'], values['LOCALE'], home):
                raise RuntimeError('Speech assets missing; run --prepare')
            managed_plist(plist, state, config)
            definition = prepared_plist.read_bytes()
            if loaded(home, plist):
                if plist.read_bytes() != definition:
                    raise RuntimeError('Receiver is active with another definition; deactivate before activation')
            else:
                if any(p.is_symlink() for p in (plist, *plist.parents)):
                    raise RuntimeError('Symlinked installation paths are unsupported')
                plist.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with tempfile.NamedTemporaryFile(dir=plist.parent, delete=False) as output:
                    output.write(definition)
                    staged_plist = Path(output.name)
                staged_plist.replace(plist)
                require(['/bin/launchctl', 'bootstrap', 'gui/' + str(os.getuid()), plist], home)
            if not loaded(home, plist):
                raise RuntimeError('Receiver activation was not verified')
            print('Receiver loaded; phone capture and worker delivery still require an end-to-end check')
            return 0
        if args.prepare:
            return prepare(args, home, config, cloud, values, queue)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, plistlib.InvalidFileException):
        # Never expose subprocess/config payloads or arbitrary filesystem diagnostics.
        error = sys.exc_info()[1]
        print('Setup failed: ' + (str(error) if type(error) is RuntimeError else 'invalid prerequisite, path, or config; no service started'), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
