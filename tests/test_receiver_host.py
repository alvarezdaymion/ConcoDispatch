"""Portable native host: isolated consumer only; no iCloud or service activation."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReceiverHostDefinitionTests(unittest.TestCase):
    def test_launchservices_waits_for_dedicated_app_with_explicit_routing_paths(self):
        from voice_kanban.build_launchagent import build_launchagent
        app = ROOT / '.local/Example Receiver.app'
        config, state = ROOT / '.local/config.sh', ROOT / '.local/state'
        definition = build_launchagent(ROOT, config=config, state=state, app=app)
        self.assertEqual(definition['ProgramArguments'], [
            '/usr/bin/open', '-W', '-g', '-a', str(app), '--args',
            '--runtime', str(ROOT), '--config', str(config), '--state', str(state),
        ])
        self.assertEqual(definition['StartInterval'], 15)
        self.assertNotIn('KeepAlive', definition)


@unittest.skipUnless(shutil.which('xcrun') and os.uname().sysname == 'Darwin', 'Mac Swift SDK required')
class NativeReceiverHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = ROOT / '.local'
        scratch.mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix='receiver-host-', dir=scratch)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.binary = cls.root / 'receiver'
        subprocess.run(['xcrun', 'swiftc', '-parse-as-library', '-module-cache-path',
                        str(scratch / 'swift-module-cache'), str(ROOT / 'native/receiver.swift'),
                        '-o', str(cls.binary)], capture_output=True, text=True, check=True)

    def test_explicit_paths_reach_only_the_isolated_consumer_and_logs(self):
        runtime, state = self.root / 'runtime', self.root / 'state'
        (runtime / 'scripts').mkdir(parents=True)
        state.mkdir()
        config = self.root / 'config.sh'
        config.write_text('# synthetic private configuration\n')
        (runtime / 'scripts/consume.sh').write_text(
            'test "$VOICE_KANBAN_CONFIG" = "$1" || :\n'
            'printf "config=%s\\nstate=%s\\ncwd=%s\\n" "$VOICE_KANBAN_CONFIG" '
            '"$VOICE_KANBAN_STATE_DIR" "$PWD"\n'
            'printf "synthetic error\\n" >&2\nexit 7\n')
        result = subprocess.run([str(self.binary), '--runtime', str(runtime), '--config',
                                 str(config), '--state', str(state)], capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual((state / 'receiver.log').read_text(),
                         'config={}\nstate={}\ncwd={}\n'.format(config, state, runtime))
        self.assertEqual((state / 'receiver-error.log').read_text(), 'synthetic error\n')
        self.assertEqual((state / 'receiver.log').stat().st_mode & 0o777, 0o600)
        self.assertEqual(result.stdout, '')
        self.assertFalse((runtime / '__pycache__').exists())

    def test_bad_arguments_do_not_launch_or_create_state(self):
        for arguments in ([], ['--runtime', 'relative'], ['--unknown', '/tmp/never'],
                          ['--runtime', '/nonexistent', '--runtime', '/duplicate']):
            with self.subTest(arguments=arguments):
                result = subprocess.run([str(self.binary), *arguments],
                                        capture_output=True, text=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Usage:', result.stderr)


if __name__ == '__main__':
    unittest.main()
