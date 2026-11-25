import os
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "publish_oraki_box3_to_flasher.py"


class PublishOrakiBox3ToFlasherTest(unittest.TestCase):
    def test_packages_firmware_and_updates_flasher_metadata(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            firmware = root / "merged-binary.bin"
            firmware.write_bytes(b"oraki firmware")
            flasher = root / "box3-web-flasher"
            (flasher / "public" / "firmware").mkdir(parents=True)
            (flasher / "src").mkdir()
            metadata = flasher / "src" / "firmware-catalog.json"
            metadata.write_text(
                json.dumps([{"id": "oraki", "version": "old", "filename": "old.zip", "url": "firmware/old.zip", "sha256": "old"}]),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--version",
                    "v2.5.3-oraki-test.1",
                    "--flasher-dir",
                    str(flasher),
                    "--firmware",
                    str(firmware),
                    "--skip-build",
                    "--skip-verify",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            archive = flasher / "public" / "firmware" / "v2.5.3-oraki-test.1.zip"
            with zipfile.ZipFile(archive) as package:
                self.assertEqual(package.namelist(), ["merged-binary.bin"])
                self.assertEqual(package.read("merged-binary.bin"), b"oraki firmware")
            entry = json.loads(metadata.read_text(encoding="utf-8"))[0]
            self.assertEqual(entry["version"], "v2.5.3-oraki-test.1")
            self.assertEqual(entry["filename"], "v2.5.3-oraki-test.1.zip")
            self.assertEqual(entry["url"], "firmware/v2.5.3-oraki-test.1.zip")
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")

    def test_refuses_to_replace_an_existing_version_without_force(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            firmware = root / "merged-binary.bin"
            firmware.write_bytes(b"new firmware")
            flasher = root / "box3-web-flasher"
            archive = flasher / "public" / "firmware" / "v1-mn7-hi-oraki.zip"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b"existing release")
            (flasher / "src").mkdir()
            (flasher / "src" / "firmware-catalog.json").write_text(
                json.dumps([{"id": "oraki"}]), encoding="utf-8"
            )

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--version",
                    "v1-mn7-hi-oraki",
                    "--flasher-dir",
                    str(flasher),
                    "--firmware",
                    str(firmware),
                    "--skip-build",
                    "--skip-verify",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("already exists", result.stderr)
            self.assertEqual(archive.read_bytes(), b"existing release")

    def test_rolls_back_the_archive_and_metadata_when_verification_fails(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            firmware = root / "merged-binary.bin"
            firmware.write_bytes(b"oraki firmware")
            flasher = root / "box3-web-flasher"
            (flasher / "public" / "firmware").mkdir(parents=True)
            (flasher / "src").mkdir()
            metadata = flasher / "src" / "firmware-catalog.json"
            original = json.dumps([{"id": "oraki", "version": "old", "filename": "old.zip", "url": "firmware/old.zip", "sha256": "old"}])
            metadata.write_text(original, encoding="utf-8")
            binary_directory = root / "bin"
            binary_directory.mkdir()
            npm = binary_directory / "npm"
            npm.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            npm.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{binary_directory}:{environment['PATH']}"

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--version",
                    "v2.5.3-oraki-mn7-hi-oraki-failed.1",
                    "--flasher-dir",
                    str(flasher),
                    "--firmware",
                    str(firmware),
                    "--skip-build",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                env=environment,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(metadata.read_text(encoding="utf-8"), original)
            self.assertFalse(
                (
                    flasher
                    / "public"
                    / "firmware"
                    / "v2.5.3-oraki-mn7-hi-oraki-failed.1.zip"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
