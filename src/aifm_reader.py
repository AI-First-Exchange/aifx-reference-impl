#!/usr/bin/env python3
"""
AIFM Reader / Validator (AIFX v0.1 - aligned)

- Reads and prints metadata/manifest.json
- Displays public_attestation.urls if present
- Optionally displays metadata/persona.txt and metadata/declaration.txt
- Verifies verification/checksums.sha256 against payload files ONLY
- Does NOT interpret persona/declaration (display-only, non-authoritative)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_sha256sum(text: str) -> List[Tuple[str, str]]:
    """
    Parses lines like:
      <hash>  payload/audio/main.mp3
    Returns list of (expected_hash, zip_path)
    """
    entries: List[Tuple[str, str]] = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if "  " in line:
            h, p = line.split("  ", 1)
            entries.append((h.strip(), p.strip()))
        else:
            parts = line.split()
            if len(parts) >= 2:
                entries.append((parts[0], parts[1]))

    return entries


def read_manifest(zf: zipfile.ZipFile) -> Dict:
    data = zf.read("metadata/manifest.json")
    return json.loads(data.decode("utf-8"))


def read_optional_text(zf: zipfile.ZipFile, path: str) -> str:
    try:
        return zf.read(path).decode("utf-8", errors="replace")
    except KeyError:
        return ""


def verify_payload_checksums(zf: zipfile.ZipFile) -> List[str]:
    """
    Verifies payload-only integrity based on verification/checksums.sha256
    Returns list of error strings; empty list means OK.
    """
    errors: List[str] = []
    checksum_text = zf.read("verification/checksums.sha256").decode("utf-8", errors="replace")
    entries = parse_sha256sum(checksum_text)

    for expected_hash, zip_path in entries:
        try:
            data = zf.read(zip_path)
        except KeyError:
            errors.append(f"Missing payload file listed in checksums: {zip_path}")
            continue

        actual_hash = sha256_bytes(data)
        if actual_hash.lower() != expected_hash.lower():
            errors.append(
                f"Hash mismatch: {zip_path}\n"
                f"  expected: {expected_hash}\n"
                f"  actual:   {actual_hash}"
            )

    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="aifm_reader.py",
        description="Read and verify an AIFM (.aifm) container (AIFX v0.1)."
    )
    parser.add_argument("aifm", type=str, help="Path to .aifm file")
    parser.add_argument("--json", action="store_true", help="Print manifest JSON only (machine-readable)")

    args = parser.parse_args(argv)
    path = Path(args.aifm).expanduser().resolve()

    if not path.exists():
        print(f"❌ File not found: {path}", file=sys.stderr)
        return 1

    try:
        with zipfile.ZipFile(path, "r") as zf:
            required_files = [
                "metadata/manifest.json",
                "verification/checksums.sha256",
                "README.txt",
            ]
            names = set(zf.namelist())
            for req in required_files:
                if req not in names:
                    print(f"❌ Missing required file: {req}", file=sys.stderr)
                    return 1

            manifest = read_manifest(zf)

            if args.json:
                print(json.dumps(manifest, indent=2, ensure_ascii=False))
                return 0

            print("✅ Manifest (authoritative):")
            print(json.dumps(manifest, indent=2, ensure_ascii=False))

            # Show public URLs if present
            pa = manifest.get("public_attestation", {}) if isinstance(manifest, dict) else {}
            urls = pa.get("urls", []) if isinstance(pa, dict) else []
            if urls:
                print("\n🔗 Public Attestation URLs (manifest):")
                for u in urls:
                    print(f"- {u}")

            # Optional metadata files
            persona = read_optional_text(zf, "metadata/persona.txt")
            if persona:
                print("\n🎭 Persona (metadata/persona.txt — non-authoritative):")
                print(persona.strip())

            declaration = read_optional_text(zf, "metadata/declaration.txt")
            if declaration:
                print("\n📜 Declaration (metadata/declaration.txt — non-authoritative):")
                print(declaration.strip())

            print("\n🔎 Verifying payload integrity (SHA-256)...")
            errors = verify_payload_checksums(zf)
            if errors:
                print("❌ Integrity check FAILED:")
                for err in errors:
                    print("-", err)
                return 2

            print("✅ Payload integrity OK")

    except zipfile.BadZipFile:
        print("❌ Invalid ZIP container (not a valid .aifm)", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 4

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
