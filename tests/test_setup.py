"""Isolated setup proofs: native tools/services are never executed."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class SetupTests(unittest.TestCase):
    def test_native_build_uses_committed_inputs_without_deploying_sources(self):
        self.platform_fixture()
        inputs = []
        def inspect_build(command, home, timeout=60):
            if 'swiftc' in command:
                source = next(Path(arg) for arg in command if str(arg).endswith('.swift'))
                (self.repo / 'native' / source.name).write_text('changed after preflight\n')
                self.assertTrue(source.is_file(), 'Compiler input was omitted from the runtime')
                self.assertEqual(source.read_bytes(), b'# synthetic source\n')
                inputs.append(source.name)
            return self.fake_run(command, home, timeout)
        with patch.object(self.setup, 'run', side_effect=inspect_build):
            code, output = self.invoke('--prepare')
        self.assertEqual(code, 0, output)
        self.assertEqual(inputs, ['receiver.swift', 'transcribe.swift'])
        self.assertFalse(list(self.state.rglob('*.swift')))

    def test_preparation_cannot_enable_intake_at_next_login(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare')[0], 0)
        installed = self.home / 'Library/LaunchAgents/io.concodispatch.receiver.plist'
        self.assertFalse(installed.exists(), 'Preparation must not create an auto-discovered agent')
        prepared = self.state / 'receiver.plist'
        self.assertTrue(prepared.is_file())
        self.assertEqual(self.invoke('--activate')[0], 0)
        self.assertEqual(installed.read_bytes(), prepared.read_bytes())

    def test_check_reports_unavailable_configured_python(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare')[0], 0)
        access = os.access
        with patch.object(self.setup.os, 'access', side_effect=lambda path, mode:
                          False if str(path) == sys.executable else access(path, mode)):
            code, output = self.invoke('--check')
        self.assertEqual(code, 1)
        self.assertIn('python: missing/not ready', output)

    def setUp(self):
        self.assertTrue((ROOT / 'scripts/setup.py').exists(), 'setup CLI is missing')
        spec = importlib.util.spec_from_file_location('conco_setup', ROOT / 'scripts/setup.py')
        assert spec is not None and spec.loader is not None
        self.setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.setup)
        (ROOT / '.local').mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / '.local')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        self.home.mkdir()
        self.state = self.home / 'Library/Application Support/Hermes Voice Kanban'
        self.config = self.state / 'config.sh'

    def test_queue_state_overlap_fails_before_any_runtime_mutation(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare')[0], 0)
        original = self.config.read_text()
        import shlex
        self.config.write_text(original.replace(shlex.quote(str(self.state)), shlex.quote(str(self.cloud / 'VoiceKanbanInbox'))))
        before = {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.calls.clear()
        code, output = self.invoke('--prepare')
        self.assertNotEqual(code, 0)
        self.assertIn('overlap', output)
        self.assertFalse(self.calls)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()})

    def test_gateway_check_accepts_native_status_prefix_and_rejects_stopped(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare')[0], 0)
        for status, ready in (('✓ Gateway is running (PID 123)', True), ('Gateway is not running', False)):
            def status_run(command, home, timeout=60):
                if str(command[0]) == str(self.hermes):
                    return subprocess.CompletedProcess(command, 0, status, '')
                return self.fake_run(command, home, timeout)
            with patch.object(self.setup, 'run', side_effect=status_run):
                code, output = self.invoke('--check')
            self.assertEqual(code, 0 if ready else 1)
            self.assertIn('gateway: ' + ('ready' if ready else 'missing/not ready'), output)

    def test_existing_config_without_python_uses_shell_default(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare')[0], 0)
        self.config.write_text('\n'.join(line for line in self.config.read_text().splitlines()
                                         if not line.startswith('export VOICE_KANBAN_PYTHON=')) + '\n')
        import argparse
        args = argparse.Namespace(home=self.home, config=self.config, hermes_bin=None,
                                  profile=None, board=None, assignee=None, locale=None)
        with patch.object(self.setup.sys, 'executable', '/some/other/python'):
            values = self.setup.settings(args)[3]
        self.assertEqual(values['PYTHON'], '/usr/bin/python3')

    def test_activation_rejects_an_unrecognized_loaded_label(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare')[0], 0)
        self.loaded = True
        with patch.object(self.setup, 'run', side_effect=self.fake_run):
            # A matching label alone is not proof that our exact plist is loaded.
            code, _ = self.invoke('--activate')
        self.assertNotEqual(code, 0)
        self.assertFalse(any('bootstrap' in c for c in self.calls))

    def test_absent_shortcut_opens_only_native_import_after_preparation(self):
        self.platform_fixture()
        self.assertNotEqual(self.invoke('--import-shortcut')[0], 0)
        self.assertEqual(self.invoke('--prepare')[0], 0)
        self.assertEqual(self.invoke('--import-shortcut')[0], 0)
        opens = [c for c in self.calls if c[0] == '/usr/bin/open']
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0][:3], ['/usr/bin/open', '-a', 'Shortcuts'])
        self.assertEqual(self.invoke('--import-shortcut')[0], 0)
        self.assertEqual(len([c for c in self.calls if c[0] == '/usr/bin/open']), 1)

    def test_missing_signed_artifact_is_not_silently_reused(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare')[0], 0)
        signed = next(self.state.rglob('ConcoDispatch.shortcut'))
        signed.unlink()
        self.assertNotEqual(self.invoke('--prepare')[0], 0)

    def test_requested_signing_identity_is_used_and_not_silently_changed(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare', '--signing-identity', 'Local Test Identity')[0], 0)
        self.assertTrue(any(c[:4] == ['/usr/bin/codesign', '--force', '--sign', 'Local Test Identity'] for c in self.calls))
        self.assertNotEqual(self.invoke('--prepare', '--signing-identity', 'Other Identity')[0], 0)

    def test_isolated_home_forbids_activation_and_import_before_tools(self):
        self.platform_fixture()
        with patch.object(self.setup.Path, 'home', return_value=self.home / 'different-real-home'):
            for mode in ('--activate', '--import-shortcut'):
                code, output = self.invoke(mode)
                self.assertNotEqual(code, 0)
                self.assertIn('isolated', output)
        self.assertFalse(self.calls)

    def test_conflicting_routing_flag_preserves_config_and_all_files(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare')[0], 0)
        before = {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.calls.clear()
        code, output = self.invoke('--prepare', '--board', 'another-board')
        self.assertNotEqual(code, 0)
        self.assertIn('BOARD', output)
        self.assertFalse(self.calls)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()})

    def test_unrecognized_plist_is_never_overwritten(self):
        self.platform_fixture()
        plist = self.home / 'Library/LaunchAgents/io.concodispatch.receiver.plist'
        plist.parent.mkdir(parents=True)
        original = plistlib.dumps({'Label': 'unrelated-service', 'ProgramArguments': ['/bin/false']})
        plist.write_bytes(original)
        self.assertNotEqual(self.invoke('--prepare')[0], 0)
        self.assertEqual(plist.read_bytes(), original)
        self.assertFalse(self.state.exists())

    def test_missing_assets_after_prepare_blocks_service_install(self):
        self.platform_fixture()
        with patch.object(self.setup, 'assets', return_value=False):
            code, output = self.invoke('--prepare')
        self.assertNotEqual(code, 0)
        self.assertIn('assets', output)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.loaded)

    def test_existing_native_helper_and_default_prepare_are_preserved(self):
        self.platform_fixture()
        helper = self.state / 'bin/transcribe'
        helper.parent.mkdir(parents=True)
        helper.write_bytes(b'existing trusted helper')
        helper.chmod(0o700)
        self.assertEqual(self.invoke()[0], 0)
        self.assertEqual(helper.read_bytes(), b'existing trusted helper')
        self.assertFalse(any(Path(arg).name == 'transcribe.swift' for c in self.calls for arg in c))

    def test_unexported_config_setting_is_rejected(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare')[0], 0)
        original = self.config.read_text().replace('export VOICE_KANBAN_BOARD=', 'VOICE_KANBAN_BOARD=')
        self.config.write_text(original)
        self.calls.clear()
        code, output = self.invoke('--prepare')
        self.assertNotEqual(code, 0)
        self.assertIn('export', output)
        self.assertFalse(self.calls)

    def test_activation_rejects_config_changed_since_preparation(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare')[0], 0)
        self.config.write_text(self.config.read_text().replace('VOICE_KANBAN_BOARD=default', 'VOICE_KANBAN_BOARD=changed'))
        code, _ = self.invoke('--activate')
        self.assertNotEqual(code, 0)
        self.assertFalse(self.loaded)

    def test_check_rejects_missing_receiver_artifacts(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare')[0], 0)
        plist = self.state / 'receiver.plist'
        plist.unlink()
        code, output = self.invoke('--check')
        self.assertNotEqual(code, 0)
        self.assertIn('receiver: missing/not ready', output)

    def test_trusted_config_timeout_is_bounded(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_text('export VOICE_KANBAN_PROFILE=default\n')
        with patch.object(self.setup.subprocess, 'run', side_effect=subprocess.TimeoutExpired('shell', 10)) as runner:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.setup.read_config(self.config, self.home)
        self.assertEqual(runner.call_args.kwargs['timeout'], 10)
        self.assertEqual(set(runner.call_args.kwargs['env']), {'HOME', 'PATH'})

    def test_trusted_shell_config_only_returns_allowlisted_settings(self):
        self.config.parent.mkdir(parents=True)
        original = b'# preserve comments\nPRIVATE_TOKEN=not-for-output\nprintf "private noise"\nexport VOICE_KANBAN_PROFILE="work space"\nexport VOICE_KANBAN_BOARD=operations\n'
        self.config.write_bytes(original)
        with patch.dict(os.environ, {'VOICE_KANBAN_ASSIGNEE': 'ambient-must-not-leak'}):
            values = self.setup.read_config(self.config, self.home)
        self.assertEqual(values, {'PROFILE': 'work space', 'BOARD': 'operations'})
        self.assertEqual(self.config.read_bytes(), original)

    def platform_fixture(self):
        self.repo = Path(self.tmp.name) / 'source'
        self.repo.mkdir()
        for name in ('voice_kanban/consumer.py', 'scripts/consume.sh', 'native/receiver.swift', 'native/transcribe.swift'):
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('# synthetic source\n')
        def git(*args):
            return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)
        git('init', '-q')
        git('config', 'user.name', 'Fixture')
        git('config', 'user.email', 'dev@example.org')
        git('add', '.')
        git('commit', '-qm', 'Synthetic setup source')
        self.cloud = self.home / 'Library/Mobile Documents/iCloud~is~workflow~my~workflows/Documents'
        self.cloud.mkdir(parents=True)
        (self.home / '.hermes').mkdir()
        self.hermes = self.home / '.local/bin/hermes'
        self.hermes.parent.mkdir(parents=True)
        self.hermes.write_text('never execute this fixture')
        self.hermes.chmod(0o700)
        self.calls, self.loaded, self.shortcut_names = [], False, []
        self.fail_tool = None
        self.addCleanup(patch.stopall)
        patch.object(self.setup, 'ROOT', self.repo).start()
        patch.object(self.setup.sys, 'platform', 'darwin').start()
        patch.object(self.setup.Path, 'home', return_value=self.home).start()
        patch.object(self.setup, 'run', side_effect=self.fake_run).start()

    def fake_run(self, command, home, timeout=60):
        command = list(map(str, command))
        self.calls.append(command)
        tool = Path(command[0]).name
        if self.fail_tool and self.fail_tool in command:
            return subprocess.CompletedProcess(command, 1, '', 'secret diagnostic must not leak')
        output, code = '', 0
        if tool == 'launchctl':
            if command[1] == 'print':
                code = 0 if self.loaded else 113
                output = ('path = ' + getattr(self, 'loaded_plist', '') + '\nstate = running') if self.loaded else ''
            elif command[1] == 'bootstrap':
                self.loaded = True
                self.loaded_plist = command[3]
            else:
                self.fail('Unexpected service mutation: ' + str(command))
        elif tool == 'xcrun':
            if 'swiftc' in command and '-o' in command:
                target = Path(command[command.index('-o') + 1])
                target.write_bytes(b'\xcf\xfa\xed\xfe synthetic Mach-O')
                target.chmod(0o700)
            else:
                output = '26.0\n'
        elif tool == 'shortcuts':
            if command[1] == 'list':
                output = '\n'.join(self.shortcut_names)
            elif command[1] == 'sign':
                Path(command[command.index('--output') + 1]).write_bytes(b'synthetic signed shortcut')
            else:
                self.fail('Unexpected Shortcuts action')
        elif tool == 'open':
            self.shortcut_names.append('ConcoDispatch')
        elif tool == 'hermes':
            self.assertEqual(command[1:], ['--profile', 'default', 'gateway', 'status'])
            output = 'Gateway is running (PID 123)\n'
        elif tool == 'transcribe' or '--check' in command or '--prepare' in command:
            output = '{"available": true, "locale_supported": true, "assets_installed": true}'
        elif tool != 'codesign':
            self.fail('Unstubbed tool: ' + str(command))
        return subprocess.CompletedProcess(command, code, output, '')

    def invoke(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = self.setup.main(['--home', str(self.home), '--hermes-bin', str(self.hermes), *args])
        return code, output.getvalue()

    def test_fresh_prepare_is_inactive_and_rerun_preserves_bytes(self):
        self.platform_fixture()
        self.assertEqual(self.invoke('--prepare')[0], 0)
        config = self.config.read_bytes()
        self.assertIn(b"VOICE_KANBAN_STT_BACKEND=apple", config)
        self.assertIn(b"VOICE_KANBAN_PROFILE=default", config)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        subprocess.run(['/bin/sh', '-n', str(self.config)], check=True)
        plist = self.state / 'receiver.plist'
        definition = plistlib.loads(plist.read_bytes())
        self.assertEqual(definition['ProgramArguments'][:4], ['/usr/bin/open', '-W', '-g', '-a'])
        app = Path(definition['ProgramArguments'][4])
        info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        self.assertEqual(info['CFBundleIdentifier'], 'io.concodispatch.receiverhost')
        self.assertEqual(info['CFBundleExecutable'], 'ConcoDispatchReceiver')
        self.assertEqual(info['CFBundleName'], 'ConcoDispatch Receiver')
        self.assertTrue((app / 'Contents/MacOS/ConcoDispatchReceiver').is_file())
        self.assertIn([str(self.state / 'bin/transcribe'), '--prepare', '--locale', 'en-US'], self.calls)
        before = {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(self.invoke('--prepare')[0], 0)
        after = {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(self.loaded)
        self.assertFalse(any(c[0].endswith('/open') or 'bootstrap' in c for c in self.calls))

    def test_apple_config_preserves_routing_and_unrelated_files(self):
        self.platform_fixture()
        self.config.parent.mkdir(parents=True)
        native = self.state / 'existing-helper'
        values = {'STT_BACKEND': 'apple', 'NATIVE_BIN': str(native), 'PYTHON': sys.executable,
                  'QUEUE_DIR': str(self.cloud / 'Nested/ExistingQueue'), 'STATE_DIR': str(self.state),
                  'PROFILE': 'default', 'BOARD': 'operations', 'ASSIGNEE': 'researcher',
                  'ENVELOPE_MARKER': 'EXISTING/7', 'LOCALE': 'en-GB', 'HERMES_BIN': str(self.hermes)}
        import shlex
        original = ('# retained verbatim\n' + ''.join('export VOICE_KANBAN_' + k + '=' + shlex.quote(v) + '\n' for k, v in values.items()) + 'PRIVATE_TOKEN=do-not-print\n').encode()
        self.config.write_bytes(original)
        for name in ('receipts.json', 'raw/capture.m4a'):
            target = self.state / name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(b'original capture')
        self.assertEqual(self.invoke('--prepare')[0], 0)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertTrue(native.is_file())
        unsigned = next(self.state.rglob('ConcoDispatch.unsigned.shortcut'))
        self.assertIn(b'Nested/ExistingQueue/', unsigned.read_bytes())
        self.assertEqual((self.state / 'receipts.json').read_bytes(), b'original capture')
        self.assertEqual((self.state / 'raw/capture.m4a').read_bytes(), b'original capture')

    def test_unsupported_or_conflicting_config_fails_before_writes(self):
        self.platform_fixture()
        self.config.parent.mkdir(parents=True)
        self.config.write_text('export VOICE_KANBAN_STT_BACKEND=whisper\n')
        before = sorted(str(p) for p in self.home.rglob('*'))
        code, output = self.invoke('--prepare')
        self.assertNotEqual(code, 0)
        self.assertIn('Apple', output)
        self.assertEqual(before, sorted(str(p) for p in self.home.rglob('*')))
        self.assertFalse(self.calls)

    def test_dirty_source_rejected_without_installation(self):
        self.platform_fixture()
        (self.repo / 'native/transcribe.swift').write_text('dirty')
        code, output = self.invoke('--prepare')
        self.assertNotEqual(code, 0)
        self.assertIn('source', output.lower())
        self.assertFalse(self.state.exists())
        self.assertFalse(self.loaded)

    def test_active_service_refused_without_stopping_or_writing(self):
        self.platform_fixture()
        self.loaded = True
        code, output = self.invoke('--prepare')
        self.assertNotEqual(code, 0)
        self.assertIn('deactivate', output.lower())
        self.assertTrue(self.loaded)
        self.assertFalse(self.state.exists())

    def test_signing_failure_does_not_activate_or_install_config(self):
        self.platform_fixture()
        self.fail_tool = 'sign'
        code, output = self.invoke('--prepare')
        self.assertNotEqual(code, 0)
        self.assertIn('shortcuts', output.lower())
        self.assertNotIn('secret diagnostic', output)
        self.assertFalse(self.config.exists())
        self.assertFalse((self.home / 'Library/LaunchAgents/io.concodispatch.receiver.plist').exists())
        self.assertFalse(self.loaded)

    def test_existing_shortcut_never_imported(self):
        self.platform_fixture()
        self.shortcut_names = ['ConcoDispatch', 'Other']
        code, _ = self.invoke('--import-shortcut')
        self.assertEqual(code, 0)
        self.assertEqual(self.calls, [['/usr/bin/shortcuts', 'list']])
        self.assertFalse(self.state.exists())

    def test_activation_requires_preparation_then_verifies_service(self):
        self.platform_fixture()
        self.assertNotEqual(self.invoke('--activate')[0], 0)
        self.assertFalse(self.loaded)
        self.assertEqual(self.invoke('--prepare')[0], 0)
        self.assertEqual(self.invoke('--activate')[0], 0)
        self.assertTrue(self.loaded)
        self.assertEqual(self.calls[-1], ['/bin/launchctl', 'print', 'gui/' + str(os.getuid()) + '/io.concodispatch.receiver'])

    def test_check_reports_missing_prerequisites_without_writes(self):
        self.platform_fixture()
        self.hermes.unlink()
        self.cloud.rmdir()
        before = sorted(str(p) for p in self.home.rglob('*'))
        code, output = self.invoke('--check')
        self.assertNotEqual(code, 0)
        for heading in ('config:', 'hermes:', 'gateway:', 'icloud:', 'sdk:', 'assets:', 'routing:'):
            self.assertIn(heading, output.lower())
        self.assertEqual(before, sorted(str(p) for p in self.home.rglob('*')))
        self.assertFalse(any('--prepare' in c or 'bootstrap' in c or 'sign' in c for c in self.calls))


if __name__ == '__main__':
    unittest.main()
