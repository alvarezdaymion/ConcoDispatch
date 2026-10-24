"""Offline native helper contract; Apple API checks need macOS/SDK 26+."""
import json
import os
import platform
import wave
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native" / "transcribe.swift"


def native_sdk_available():
    if platform.system() != "Darwin" or not shutil.which("xcrun"):
        return False
    if int(platform.mac_ver()[0].split(".")[0]) < 26:
        return False
    sdk = subprocess.run(
        ["xcrun", "--sdk", "macosx", "--show-sdk-version"],
        capture_output=True, text=True, timeout=30,
    )
    return sdk.returncode == 0 and int(sdk.stdout.split(".")[0]) >= 26


class NativeSourceTests(unittest.TestCase):
    def test_missing_assets_requires_a_supported_locale(self):
        case = NativeSpeechTests("test_missing_assets_do_not_trigger_download")
        (ROOT / ".local").mkdir(exist_ok=True)
        work = tempfile.TemporaryDirectory(dir=ROOT / ".local")
        self.addCleanup(work.cleanup)
        case.work = work
        payload = {"available": True, "locale_supported": False, "assets_installed": False}
        with patch.object(case, "run_helper", return_value=subprocess.CompletedProcess(
                [], 0, json.dumps(payload), "")) as run:
            with self.assertRaises(unittest.SkipTest):
                case.test_missing_assets_do_not_trigger_download()
        self.assertEqual(run.call_count, 1)

    def test_compiler_cache_stays_in_isolated_work_directory(self):
        case = type("SyntheticSpeechTests", (NativeSpeechTests,), {})
        try:
            with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
                case.setUpClass()
            command = run.call_args.args[0]
            self.assertIn("-module-cache-path", command)
            cache = Path(command[command.index("-module-cache-path") + 1])
            cache.relative_to(Path(case.work.name))
        finally:
            case.doClassCleanups()

    def test_native_helper_is_shipped(self):
        self.assertTrue(SOURCE.is_file(), "native/transcribe.swift is missing")


@unittest.skipUnless(native_sdk_available(), "requires macOS and SDK 26+")
class NativeSpeechTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / ".local").mkdir(exist_ok=True)
        cls.work = tempfile.TemporaryDirectory(prefix="native-tests-", dir=ROOT / ".local")
        cls.addClassCleanup(cls.work.cleanup)
        cls.binary = Path(cls.work.name) / "transcribe"
        compiled = subprocess.run(
            ["xcrun", "swiftc", "-parse-as-library", "-module-cache-path",
             str(Path(cls.work.name) / "swift-module-cache"), "-target",
             platform.machine() + "-apple-macos26.0", str(SOURCE), "-o", str(cls.binary)],
            capture_output=True, text=True, timeout=180,
        )
        if compiled.returncode:
            raise AssertionError("native helper compilation failed:\n" + compiled.stderr)

    def run_helper(self, *args):
        return subprocess.run(
            [str(self.binary), *map(str, args)], capture_output=True, text=True, timeout=60,
        )

    def test_invalid_arguments_fail_without_json(self):
        for args in [(), ("--bogus",), ("--locale",), ("--check", "file.wav"),
                     ("--check", "--prepare"), ("one.wav", "two.wav")]:
            with self.subTest(args=args):
                result = self.run_helper(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("Usage:", result.stderr)

    def test_unsupported_locale_is_reported_and_not_transcribed(self):
        result = self.run_helper("--check", "--locale", "zz-ZZ")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["locale"], "zz-ZZ")
        self.assertFalse(payload["locale_supported"])
        self.assertFalse(payload["assets_installed"])
        result = self.run_helper("--locale", "zz-ZZ", "unused.wav")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("unsupported locale" if payload['available'] else 'unavailable', result.stderr.lower())

    def test_missing_or_invalid_audio_is_an_error_not_a_transcript(self):
        invalid = Path(self.work.name) / "invalid.wav"
        invalid.write_bytes(b"not an audio file")
        for path in [Path(self.work.name) / "missing.wav", invalid]:
            with self.subTest(path=path):
                result = self.run_helper(path)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.strip())

    def test_missing_assets_do_not_trigger_download(self):
        before = json.loads(self.run_helper("--check").stdout)
        if not before["available"] or not before["locale_supported"] or before["assets_installed"]:
            self.skipTest("requires a supported en-US transcriber without installed assets")
        silence = Path(self.work.name) / "silence.wav"
        with wave.open(str(silence), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\x00\x00" * 16000)
        result = self.run_helper(silence)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("--prepare", result.stderr)
        after = json.loads(self.run_helper("--check").stdout)
        self.assertFalse(after["assets_installed"])

    def test_silence_fails_without_a_success_payload(self):
        check = json.loads(self.run_helper('--check').stdout)
        if not check['assets_installed']:
            self.skipTest('requires already installed speech assets; never downloads')
        silence = Path(self.work.name) / 'silence.wav'
        with wave.open(str(silence), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b'\x00\x00' * 16000)
        result = self.run_helper(silence)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertIn('empty', result.stderr.lower())

    @unittest.skipUnless(os.environ.get("NATIVE_SPEECH_PREPARE") == "1",
                         "explicit opt-in required for Apple asset download")
    def test_prepare_installs_assets_and_readback_confirms(self):
        result = subprocess.run([str(self.binary), "--prepare"],
                                capture_output=True, text=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["assets_installed"])
        check = self.run_helper("--check")
        self.assertTrue(json.loads(check.stdout)["assets_installed"])

    @unittest.skipUnless(os.environ.get("NATIVE_SPEECH_PROOF") == "1",
                         "explicit opt-in required for synthetic audio proof")
    def test_real_file_retains_beginning_pause_and_end(self):
        ffmpeg = shutil.which("ffmpeg")
        self.assertIsNotNone(ffmpeg, "proof requires ffmpeg")
        proof = ROOT / ".local" / "native-proof"
        proof.mkdir(parents=True, exist_ok=True)
        narration = [
            "Purple lantern opens this recording. This is a synthetic note for an offline "
            "speech recognition test. The first task is to review the calendar and write "
            "down the questions for tomorrow. Keep the original recording intact and "
            "wait for every sentence to finish. I am about to pause while I think about "
            "the next part of the plan.",
            "After a quiet pause, the second task is to compare the notes and identify "
            "the next useful action. No messages should be sent and no appointments "
            "should be created during this test. The final sentence matters as much "
            "as the beginning. Please keep all of these words in the completed transcript. "
            "Silver compass closes this recording.",
        ]
        narration[0] += (' Keep a written list of the project questions. Compare each question with the original notes. '
                         'Retain the full context and do not take external actions during this synthetic test.') * 16
        commands = []

        def run(command):
            commands.append(list(map(str, command)))
            result = subprocess.run(commands[-1], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)

        for index, text in enumerate(narration):
            run(["/usr/bin/say", "-v", "Samantha", "-r", "165", "-o",
                 proof / (str(index) + ".aiff"), text])
        run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
             "-i", proof / "0.aiff", "-f", "lavfi", "-i",
             "anullsrc=r=48000:cl=mono:d=6", "-i", proof / "1.aiff",
             "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
             "-map", "[out]", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
             proof / "narration.wav"])
        run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
             "-i", proof / "narration.wav", "-c:a", "aac", proof / "narration.m4a"])
        with wave.open(str(proof / "narration.wav"), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
        started = time.monotonic()
        result = self.run_helper("--locale", "en-US", proof / "narration.m4a")
        elapsed = time.monotonic() - started
        (proof / "stdout.json").write_text(result.stdout)
        (proof / "stderr.txt").write_text(result.stderr)
        (proof / "receipt.json").write_text(json.dumps({
            "commands": commands, "duration_seconds": duration, "pause_seconds": 6,
            "elapsed_seconds": elapsed, "exit_code": result.returncode,
        }, indent=2) + "\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(set(payload), {"text"})
        words = " ".join("".join(c if c.isalnum() else " " for c in payload["text"].lower()).split())
        self.assertTrue(words.startswith("purple lantern opens this recording"), words)
        self.assertIn("after a quiet pause", words)
        self.assertTrue(words.endswith("silver compass closes this recording"), words)
        self.assertEqual(words.count("purple lantern"), 1)
        self.assertEqual(words.count("silver compass"), 1)
        self.assertEqual(result.stderr, "")

    def test_check_reports_availability_without_installing_assets(self):
        result = self.run_helper("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIs(type(payload["available"]), bool)
        self.assertIs(type(payload["assets_installed"]), bool)
        self.assertEqual(payload["locale"], "en-US")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
