import unittest
from pathlib import Path
from unittest.mock import patch
from voice_kanban.build_shortcut import build_workflow, main


class AudioShortcutTests(unittest.TestCase):
    def test_removed_cli_capture_paths_are_rejected(self):
        for arguments in (['--platform', 'mac'], ['--capture-mode', 'dictation']):
            with self.subTest(arguments=arguments), patch('sys.argv', ['build_shortcut'] + arguments), \
                    patch('voice_kanban.build_shortcut.write_unsigned') as writer, \
                    patch('sys.stderr'), patch('builtins.print'):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)
                writer.assert_not_called()

    def test_new_mac_audio_path_uses_shared_queue_not_direct_triage(self):
        import plistlib
        import tempfile
        from voice_kanban.build_shortcut import write_unsigned
        scratch = Path(__file__).resolve().parents[1] / '.local'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            path = write_unsigned(Path(tmp) / 'mac-audio.shortcut', platform='mac-audio', queue_folder='SharedInbox/')
            workflow = plistlib.loads(path.read_bytes())
        identifiers = [action['WFWorkflowActionIdentifier'] for action in workflow['WFWorkflowActions']]
        self.assertEqual(identifiers[0], 'is.workflow.actions.recordaudio')
        self.assertIn('is.workflow.actions.documentpicker.save', identifiers)
        self.assertNotIn('is.workflow.actions.runapplescript', identifiers)
        self.assertIn('SharedInbox/', repr(workflow))

    def test_cli_default_names_preserve_audio_shortcuts_and_explicit_output(self):
        for arguments, expected in (
            ([], Path('dist/ConcoDispatch.unsigned.shortcut')),
            (['--platform', 'mac-audio'], Path('dist/ConcoDispatch Mac.unsigned.shortcut')),
            (['--output', 'custom.shortcut'], Path('custom.shortcut')),
        ):
            with self.subTest(arguments=arguments), \
                    patch('sys.argv', ['build_shortcut'] + arguments), \
                    patch('voice_kanban.build_shortcut.write_unsigned') as writer, \
                    patch('builtins.print'):
                self.assertEqual(main(), 0)
                self.assertEqual(writer.call_args.args[0], expected)

    def test_default_is_immediate_manual_stop_audio_without_live_dictation(self):
        actions = build_workflow()['WFWorkflowActions']
        identifiers = [a['WFWorkflowActionIdentifier'] for a in actions]
        self.assertEqual(identifiers[0], 'is.workflow.actions.recordaudio')
        self.assertNotIn('is.workflow.actions.dictatetext', identifiers)
        recording = actions[0]['WFWorkflowActionParameters']
        self.assertEqual(recording['WFRecordingStart'], 'Immediately')
        self.assertEqual(recording['WFRecordingEnd'], 'On Tap')
        self.assertNotIn('WFRecordingTimeInterval', recording)

    def test_audio_flows_to_named_m4a_then_literal_queue_without_picker(self):
        actions = build_workflow(queue_folder='TestInbox/')['WFWorkflowActions']
        by_name = {a['WFWorkflowActionIdentifier']: a['WFWorkflowActionParameters'] for a in actions}
        named = by_name['is.workflow.actions.setitemname']
        self.assertEqual(named['WFInput']['Value']['OutputName'], 'Recorded Audio')
        self.assertTrue(named['WFName']['Value']['string'].endswith('.m4a'))
        self.assertEqual({v['OutputName'] for v in named['WFName']['Value']['attachmentsByRange'].values()}, {'Capture ID'})
        saved = by_name['is.workflow.actions.documentpicker.save']
        self.assertFalse(saved['WFAskWhereToSave'])
        self.assertFalse(saved['WFSaveFileOverwrite'])
        self.assertEqual(saved['WFFileDestinationPath']['Value'], {'string': 'TestInbox/', 'attachmentsByRange': {}})
        self.assertEqual(saved['WFInput']['Value']['OutputName'], 'Named Capture')
        self.assertNotIn('Capture Envelope', repr(actions))
        queued = next(a['WFWorkflowActionParameters'] for a in actions
                      if a['WFWorkflowActionParameters'].get('WFNotificationActionTitle') == 'Saved to Voice Queue')
        self.assertIn('pending', repr(queued).lower())

    def test_capture_identity_uses_date_and_random_number(self):
        actions = build_workflow()['WFWorkflowActions']
        params = {a['WFWorkflowActionIdentifier']: a['WFWorkflowActionParameters'] for a in actions}
        random = params['is.workflow.actions.number.random']
        self.assertEqual((random['WFRandomNumberMinimum'], random['WFRandomNumberMaximum']),
                         (100000000, 999999999))
        capture = params['is.workflow.actions.gettext']['WFTextActionText']['Value']
        self.assertEqual({a['OutputName'] for a in capture['attachmentsByRange'].values()},
                         {'Formatted Date', 'Random Number'})

    def test_unsafe_queue_path_and_removed_platform_are_rejected(self):
        for folder in ('../outside', '/absolute', 'a/../../b', ''):
            with self.assertRaises(ValueError):
                build_workflow(queue_folder=folder)
        from voice_kanban.build_shortcut import write_unsigned
        with self.assertRaises(ValueError):
            write_unsigned(Path('must-not-exist.shortcut'), platform='mac')


if __name__ == '__main__':
    unittest.main()
