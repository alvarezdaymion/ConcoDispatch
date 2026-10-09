#!/usr/bin/env python3
"""Build audio-first mobile and baseline Mac Shortcuts from inspectable source."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import uuid

QUEUE_FOLDER = "VoiceKanbanInbox/"
ENVELOPE_MARKER = "VOICEKANBAN/2"


def uid() -> str:
    return str(uuid.uuid4()).upper()


def output_ref(output_uuid: str, output_name: str) -> dict:
    return {"Value": {"OutputName": output_name, "OutputUUID": output_uuid,
                      "Type": "ActionOutput"},
            "WFSerializationType": "WFTextTokenAttachment"}


def token_string(*parts: str | tuple[str, str]) -> dict:
    rendered = ""
    attachments = {}
    for part in parts:
        if isinstance(part, str):
            rendered += part
        else:
            output_uuid, output_name = part
            position = len(rendered.encode("utf-16-le")) // 2
            rendered += "\uFFFC"
            attachments[f"{{{position}, 1}}"] = {
                "OutputName": output_name, "OutputUUID": output_uuid, "Type": "ActionOutput",
            }
    return {"Value": {"attachmentsByRange": attachments, "string": rendered},
            "WFSerializationType": "WFTextTokenString"}


def action(identifier: str, **parameters) -> dict:
    return {"WFWorkflowActionIdentifier": "is.workflow.actions." + identifier,
            "WFWorkflowActionParameters": parameters}


def notification(title: str, body: str | dict) -> dict:
    return action("notification", UUID=uid(), WFNotificationActionTitle=title,
                  WFNotificationActionBody=body, WFNotificationActionSound=True)


def workflow_metadata(actions: list[dict]) -> dict:
    return {
        "WFQuickActionSurfaces": [],
        "WFWorkflowActions": actions,
        "WFWorkflowClientVersion": "2607.0.4",
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowHasShortcutInputVariables": False,
        "WFWorkflowIcon": {"WFWorkflowIconGlyphNumber": 59667,
                           "WFWorkflowIconStartColor": -1263359489},
        "WFWorkflowImportQuestions": [],
        "WFWorkflowInputContentItemClasses": ["WFStringContentItem"],
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowTypes": [],
    }


def build_workflow(queue_folder: str = QUEUE_FOLDER,
                   envelope_marker: str = ENVELOPE_MARKER, capture_mode: str = "audio") -> dict:
    """Mobile: immediate audio, deliberate Stop, named file, literal iCloud folder."""
    if capture_mode not in {"audio", "dictation"}:
        raise ValueError("Capture mode must be audio or dictation")
    if not envelope_marker or "\n" in envelope_marker or "\r" in envelope_marker:
        raise ValueError("Envelope marker must be a nonempty single line")
    if not queue_folder or queue_folder.startswith("/") or ".." in queue_folder.split("/"):
        raise ValueError("Queue folder must be relative to iCloud Drive/Shortcuts")
    queue_folder = queue_folder.rstrip("/") + "/"
    recording, group, date, formatted, random, capture, envelope, named = [uid() for _ in range(8)]
    output_name = "Recorded Audio" if capture_mode == "audio" else "Dictated Text"
    capture_action = (action("recordaudio", CustomOutputName=output_name, UUID=recording,
                            WFRecordingStart="Immediately", WFRecordingEnd="On Tap")
                      if capture_mode == "audio" else
                      action("dictatetext", CustomOutputName=output_name, UUID=recording,
                             WFDictateTextActionStartImmediately=True, WFSpeechLanguage="en-US",
                             WFDictateTextStopListening="On Tap"))
    actions = [
        capture_action,
        action("conditional", GroupingIdentifier=group, WFCondition=100, WFControlFlowMode=0,
               WFInput={"Type": "Variable", "Variable": output_ref(recording, output_name)}),
        action("date", CustomOutputName="Date", UUID=date, WFDateActionMode="Current Date"),
        action("format.date", CustomOutputName="Formatted Date", UUID=formatted,
               WFDate=output_ref(date, "Date"), WFDateFormatStyle="Custom",
               WFDateFormat="yyyyMMdd'T'HHmmssSSS", WFTimeFormatStyle="None"),
        action("number.random", CustomOutputName="Random Number", UUID=random,
               WFRandomNumberMinimum=100000000, WFRandomNumberMaximum=999999999),
        action("gettext", CustomOutputName="Capture ID", UUID=capture,
               WFTextActionText=token_string("capture-", (formatted, "Formatted Date"),
                                            "-", (random, "Random Number"))),
    ]
    if capture_mode == "dictation":
        actions.append(action("gettext", CustomOutputName="Capture Envelope", UUID=envelope,
               WFTextActionText=token_string(envelope_marker + "\ncapture_id: ",
                                            (capture, "Capture ID"), "\ncaptured_at: ",
                                            (date, "Date"), "\n---\n", (recording, output_name))))
    named_input = (output_ref(recording, output_name) if capture_mode == "audio"
                   else output_ref(envelope, "Capture Envelope"))
    actions.extend([
        action("setitemname", CustomOutputName="Named Capture", UUID=named,
               WFInput=named_input,
               WFName=token_string((capture, "Capture ID"), ".m4a" if capture_mode == "audio" else ".txt"),
               WFDontIncludeFileExtension=False),
        action("documentpicker.save", UUID=uid(), WFInput=output_ref(named, "Named Capture"),
               WFAskWhereToSave=False, WFFileStorageService="iCloud Drive",
               WFSaveFileOverwrite=False, WFFileDestinationPath=token_string(queue_folder)),
        notification("Saved to Voice Queue", token_string(
            "Capture ", (capture, "Capture ID"),
            " is saved to the iCloud queue; Kanban confirmation is pending.")),
        action("conditional", GroupingIdentifier=group, WFControlFlowMode=1),
        notification("Nothing captured", "No queue file was created. Hold the Action Button and try again."),
        action("conditional", GroupingIdentifier=group, UUID=uid(), WFControlFlowMode=2),
    ])
    return workflow_metadata(actions)


def build_mac_workflow() -> dict:
    """Mac: Dictate Text -> AppleScript direct triage -> output, no mobile queue."""
    dictation, script_output = uid(), uid()
    script = (Path(__file__).resolve().parents[1] / "shortcuts/mac_capture.applescript").read_text()
    return workflow_metadata([
        action("dictatetext", WFDictateTextLanguage="en-US", WFDictateTextStopListening="On Tap",
               CustomOutputName="Dictated Text", UUID=dictation,
               WFDictateTextActionStartImmediately=True),
        action("runapplescript", Input=output_ref(dictation, "Dictated Text"),
               Script=script, UUID=script_output),
        action("output", WFOutput=token_string((script_output, "AppleScript Result")), UUID=uid()),
    ])


def write_unsigned(path: Path, *, platform: str = "mobile", queue_folder: str = QUEUE_FOLDER,
                   envelope_marker: str = ENVELOPE_MARKER, capture_mode: str = "audio") -> Path:
    if platform not in ("mobile", "mac"):
        raise ValueError("Platform must be mobile or mac")
    workflow = (build_mac_workflow() if platform == "mac" else
                build_workflow(queue_folder, envelope_marker, capture_mode))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(workflow, handle, fmt=plistlib.FMT_BINARY, sort_keys=False)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("mobile", "mac"), default="mobile")
    parser.add_argument("--capture-mode", choices=("audio", "dictation"), default="audio",
                        help="Mobile mode; Mac retains its dictation baseline")
    parser.add_argument("--queue-folder", default=os.environ.get("VOICE_KANBAN_QUEUE_FOLDER", QUEUE_FOLDER),
                        help="Literal folder relative to iCloud Drive/Shortcuts")
    parser.add_argument("--envelope-marker", default=os.environ.get("VOICE_KANBAN_ENVELOPE_MARKER", ENVELOPE_MARKER))
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    output = arguments.output or Path("dist") / f"Hermes Voice Kanban {arguments.platform.title()}.unsigned.shortcut"
    print(write_unsigned(output, platform=arguments.platform, queue_folder=arguments.queue_folder,
                         envelope_marker=arguments.envelope_marker, capture_mode=arguments.capture_mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
