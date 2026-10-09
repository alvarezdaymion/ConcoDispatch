"""Routing/deadline contracts; never address a real board or service."""
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from voice_kanban import consumer


class ReceiverRoutingTests(unittest.TestCase):
    def test_notification_uses_the_receipts_profile(self):
        with patch.object(consumer, 'NOTIFY_TARGET', 'synthetic-destination'), \
                patch.object(consumer, 'run_command') as run:
            consumer.notify('synthetic-capture', 't_synthetic', 'Synthetic text', profile='synthetic-profile')
        self.assertEqual(run.call_args.args[0][1:6], ['--profile', 'synthetic-profile', 'send', '--to', 'synthetic-destination'])

    def test_cli_deadline_is_bounded_and_timeout_is_recoverable(self):
        with patch.dict(os.environ, {'VOICE_KANBAN_CLI_TIMEOUT': '0.1'}), \
                patch.object(consumer.subprocess, 'run', return_value=SimpleNamespace(stdout='{}')) as run:
            self.assertEqual(consumer.run_json(['synthetic-hermes', 'kanban', 'list']), {})
        self.assertEqual(run.call_args.kwargs['timeout'], 0.1)
        with patch.object(consumer.subprocess, 'run', side_effect=subprocess.TimeoutExpired('synthetic', 30)):
            with self.assertRaises(consumer.CaptureError):
                consumer.run_json(['synthetic-hermes'])


if __name__ == '__main__':
    unittest.main()
