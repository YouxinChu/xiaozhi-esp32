#!/usr/bin/env python3
"""Build, package, and publish the Oraki BOX-3B firmware to the web flasher."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FLASHER_DIR = PROJECT_ROOT.parent / "box3-web-flasher"
VERSION_PATTERN = re.compile(r"^v[0-9A-Za-z][0-9A-Za-z._-]*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Oraki BOX-3B firmware and publish it to box3-web-flasher."
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Unique release version, for example v2.5.3-oraki-20261125.1",
    )
    parser.add_argument("--flasher-dir", type=Path, default=DEFAULT_FLASHER_DIR)
    parser.add_argument(
        "--firmware",
        type=Path,
        default=PROJECT_ROOT / "build" / "merged-binary.bin",
    )
    parser.add_argument("--force", action="store_true", help="Replace an existing version")
    parser.add_argument("--skip-build", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-verify", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def run_build() -> None:
    environment = os.environ.copy()
    if environment.get("IDF_PATH"):
        subprocess.run(
            [str(PROJECT_ROOT / "scripts" / "build_oraki_box3.sh")],
            cwd=PROJECT_ROOT,
            env=environment,
            check=True,
        )
        return

    export_script = Path.home() / "esp" / "esp-idf" / "export.sh"
    if not export_script.is_file():
        fail("ESP-IDF is not active; source export.sh or install it under ~/esp/esp-idf")
    command = f'source "{export_script}" && ./scripts/build_oraki_box3.sh'
    subprocess.run(["bash", "-lc", command], cwd=PROJECT_ROOT, check=True)


def package_firmware(firmware: Path, destination: Path) -> str:
    if not firmware.is_file():
        fail(f"firmware not found: {firmware}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
    try:
        with zipfile.ZipFile(
            temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            archive.write(firmware, arcname="merged-binary.bin")
        digest = hashlib.sha256(temporary_path.read_bytes()).hexdigest()
        temporary_path.replace(destination)
        return digest
    finally:
        temporary_path.unlink(missing_ok=True)


def update_flasher_metadata(metadata: Path, version: str, filename: str, digest: str) -> None:
    if not metadata.is_file():
        fail(f"flasher metadata not found: {metadata}")
    try:
        catalog = json.loads(metadata.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        fail(f"invalid firmware catalog {metadata}: {error}")
    if not isinstance(catalog, list):
        fail(f"firmware catalog must be a JSON array: {metadata}")
    entry = next(
        (candidate for candidate in catalog if isinstance(candidate, dict) and candidate.get("id") == "oraki"),
        None,
    )
    if entry is None:
        fail(f"oraki entry not found in firmware catalog: {metadata}")
    entry.update(
        version=version,
        filename=filename,
        url=f"firmware/{filename}",
        sha256=digest,
    )
    metadata.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def verify_flasher(flasher_dir: Path) -> None:
    subprocess.run(["npm", "test", "--", "src/firmware.test.ts"], cwd=flasher_dir, check=True)
    subprocess.run(["npm", "run", "build"], cwd=flasher_dir, check=True)


def main() -> None:
    args = parse_args()
    if not VERSION_PATTERN.fullmatch(args.version):
        fail("version must start with 'v' and contain only letters, numbers, '.', '_' or '-'")

    flasher_dir = args.flasher_dir.resolve()
    filename = f"{args.version}.zip"
    destination = flasher_dir / "public" / "firmware" / filename
    if destination.exists() and not args.force:
        fail(f"release already exists: {destination}; use --force to replace it")

    if not args.skip_build:
        run_build()

    metadata = flasher_dir / "src" / "firmware-catalog.json"
    if not metadata.is_file():
        fail(f"flasher metadata not found: {metadata}")
    original_metadata = metadata.read_bytes()
    original_archive = destination.read_bytes() if destination.exists() else None
    try:
        digest = package_firmware(args.firmware.resolve(), destination)
        update_flasher_metadata(metadata, args.version, filename, digest)
        if not args.skip_verify:
            verify_flasher(flasher_dir)
    except BaseException:
        metadata.write_bytes(original_metadata)
        if original_archive is None:
            destination.unlink(missing_ok=True)
        else:
            destination.write_bytes(original_archive)
        raise

    print(f"Published Oraki BOX-3B firmware: {destination}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
