import unittest
from voice_kanban.build_shortcut import build_workflow


class AudioShortcutTests(unittest.TestCase):
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

    def test_dictation_baseline_can_still_be_rebuilt(self):
        actions = build_workflow(capture_mode='dictation')['WFWorkflowActions']
        self.assertEqual(actions[0]['WFWorkflowActionIdentifier'], 'is.workflow.actions.dictatetext')
        self.assertIn('VOICEKANBAN/2', repr(actions))

    def test_invalid_capture_mode_and_unsafe_queue_path_are_rejected(self):
        for mode in ('unknown', ''):
            with self.assertRaises(ValueError):
                build_workflow(capture_mode=mode)
        for folder in ('../outside', '/absolute', 'a/../../b', ''):
            with self.assertRaises(ValueError):
                build_workflow(queue_folder=folder)


if __name__ == '__main__':
    unittest.main()
