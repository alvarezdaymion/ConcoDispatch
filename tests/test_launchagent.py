"""Launchd definitions are generated only; tests never load a service."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LaunchAgentTests(unittest.TestCase):

    def test_receiver_runs_nonoverlapping_bounded_passes(self):
        from voice_kanban.build_launchagent import build_launchagent
        definition = build_launchagent(ROOT, config=Path.home() / 'config.sh')
        self.assertEqual(definition['ProgramArguments'], ['/bin/sh', str(ROOT / 'scripts/consume.sh')])
        self.assertEqual(definition['StartInterval'], 15)
        self.assertTrue(definition['RunAtLoad'])
        self.assertNotIn('KeepAlive', definition)
        self.assertEqual(definition['EnvironmentVariables']['VOICE_KANBAN_CONFIG'], str(Path.home() / 'config.sh'))
        self.assertIn('PATH', definition['EnvironmentVariables'])

        self.assertEqual(definition['Umask'], 0o077)


if __name__ == '__main__':
    unittest.main()
