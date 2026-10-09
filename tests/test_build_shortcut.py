from pathlib import Path
import plistlib
import tempfile
import unittest

from voice_kanban.build_shortcut import build_workflow, build_mac_workflow, write_unsigned

ROOT = Path(__file__).resolve().parents[1]


class ShortcutBuilderTests(unittest.TestCase):
    def test_capture_id_embedded_in_envelope_and_filename_before_literal_folder_save(self):
        actions = build_workflow()["WFWorkflowActions"]
        params = lambda name: next(a["WFWorkflowActionParameters"] for a in actions
                                  if a["WFWorkflowActionIdentifier"] == "is.workflow.actions." + name)
        texts = {a["WFWorkflowActionParameters"].get("CustomOutputName"): a["WFWorkflowActionParameters"]
                 for a in actions if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.gettext"}
        random = params("number.random")
        self.assertEqual((random["WFRandomNumberMinimum"], random["WFRandomNumberMaximum"]),
                         (100000000, 999999999))
        capture = texts["Capture ID"]["WFTextActionText"]["Value"]
        self.assertEqual({a["OutputName"] for a in capture["attachmentsByRange"].values()},
                         {"Formatted Date", "Random Number"})
        envelope = texts["Capture Envelope"]["WFTextActionText"]["Value"]
        self.assertTrue(envelope["string"].startswith("VOICEKANBAN/2\n"))
        self.assertEqual({a["OutputName"] for a in envelope["attachmentsByRange"].values()},
                         {"Capture ID", "Date", "Dictated Text"})
        named = params("setitemname")
        self.assertEqual(named["WFInput"]["Value"]["OutputName"], "Capture Envelope")
        self.assertEqual({a["OutputName"] for a in named["WFName"]["Value"]["attachmentsByRange"].values()},
                         {"Capture ID"})
        self.assertTrue(named["WFName"]["Value"]["string"].endswith(".txt"))
        save = params("documentpicker.save")
        destination = save["WFFileDestinationPath"]
        self.assertEqual(destination["WFSerializationType"], "WFTextTokenString")
        self.assertEqual(destination["Value"], {"string": "VoiceKanbanInbox/", "attachmentsByRange": {}})
        self.assertFalse(save["WFSaveFileOverwrite"])
        self.assertFalse(save["WFAskWhereToSave"])
        self.assertEqual(save["WFInput"]["Value"]["OutputName"], "Named Capture")
        self.assertEqual(params("dictatetext")["WFDictateTextStopListening"], "On Tap")
        notification = params("notification")
        self.assertEqual(notification["WFNotificationActionTitle"], "Saved to Voice Queue")
        self.assertIn("pending", repr(notification["WFNotificationActionBody"]))
        self.assertNotIn("Telegram", repr(notification))

    def test_mobile_builder_allows_local_folder_and_marker(self):
        workflow = build_workflow(queue_folder="LocalInbox/", envelope_marker="LOCALVOICE/2")
        content = repr(workflow)
        self.assertIn("LocalInbox/", content)
        self.assertIn("LOCALVOICE/2", content)
        self.assertNotIn("VoiceKanbanInbox/", content)

    def test_mac_preserves_dictation_applescript_output_and_triage(self):
        actions = build_mac_workflow()["WFWorkflowActions"]
        self.assertEqual([a["WFWorkflowActionIdentifier"] for a in actions],
                         ["is.workflow.actions.dictatetext", "is.workflow.actions.runapplescript",
                          "is.workflow.actions.output"])
        self.assertEqual(actions[0]["WFWorkflowActionParameters"]["WFDictateTextStopListening"], "On Tap")
        script = actions[1]["WFWorkflowActionParameters"]["Script"]
        self.assertIn("--triage --created-by mac-voice-capture --json", script)
        self.assertIn("path to home folder", script)
        self.assertIn("quoted form of capturedText", script)
        self.assertIn("VOICE_KANBAN_HERMES_BIN", script)
        self.assertIn("config.sh", script)

    def test_generated_shortcuts_roundtrip_as_plists(self):
        scratch = ROOT / ".local"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            for platform in ("mobile", "mac"):
                path = write_unsigned(Path(tmp) / f"{platform}.shortcut", platform=platform)
                workflow = plistlib.loads(path.read_bytes())
                self.assertTrue(workflow["WFWorkflowActions"])


if __name__ == "__main__":
    unittest.main()
