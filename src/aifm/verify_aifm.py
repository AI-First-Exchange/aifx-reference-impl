#!/usr/bin/env python3
"""
AIFX AIFM Verifier — v0.2 (hash-check)

Usage:
  python3 SRC/verify_aifm.py /path/to/file.aifm [--verbose]

What it does:
- Opens the .aifm (zip container)
- Reads manifest.json
- Verifies sha256 + bytes for every entry in integrity.hashed_files
- Special case: manifest.json uses canonical_excludes_self mode
  - For manifest.json we verify the canonical hash
  - We DO NOT fail on bytes mismatch (zip tools/editors may reformat JSON)
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile


@dataclass
class CheckResult:
    ok: bool
    path: str
    reason: str = ""


def sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def read_zip_bytes(z: ZipFile, member: str) -> bytes:
    with z.open(member, "r") as f:
        return f.read()


def canonical_manifest_bytes(manifest: dict, mode: str) -> bytes:
    if mode != "canonical_excludes_self":
        raise ValueError(f"Unsupported manifest_hash_mode: {mode}")

    m = json.loads(json.dumps(manifest, ensure_ascii=False))  # deep-ish copy
    try:
        m["integrity"]["hashed_files"].pop("manifest.json", None)
    except Exception:
        pass

    return json.dumps(m, indent=2, ensure_ascii=False).encode("utf-8")


def verify(aifm_path: Path) -> tuple[bool, list[CheckResult]]:
    if not aifm_path.exists():
        raise FileNotFoundError(aifm_path)

    results: list[CheckResult] = []

    with ZipFile(aifm_path, "r") as z:
        if "manifest.json" not in z.namelist():
            raise ValueError("Missing manifest.json in AIFM")

        manifest_bytes_in_zip = read_zip_bytes(z, "manifest.json")
        try:
            manifest = json.loads(manifest_bytes_in_zip.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Invalid manifest.json (not valid JSON): {e}")

        integrity = manifest.get("integrity") or {}
        algo = (integrity.get("algorithm") or "").lower()
        hashed_files = integrity.get("hashed_files") or {}
        mode = integrity.get("manifest_hash_mode") or ""

        if algo != "sha256":
            raise ValueError(f"Unsupported integrity.algorithm: {algo!r} (expected 'sha256')")
        if not isinstance(hashed_files, dict) or not hashed_files:
            raise ValueError("integrity.hashed_files missing or empty")

        for member, info in hashed_files.items():
            if not isinstance(info, dict):
                results.append(CheckResult(False, member, "hash record is not an object"))
                continue

            expected_hash = (info.get("sha256") or "").strip().lower()
            expected_bytes = info.get("bytes")

            if not expected_hash or len(expected_hash) != 64:
                results.append(CheckResult(False, member, "missing/invalid expected sha256"))
                continue
            if not isinstance(expected_bytes, int) or expected_bytes < 0:
                results.append(CheckResult(False, member, "missing/invalid expected bytes"))
                continue

            if member == "manifest.json":
                if mode != "canonical_excludes_self":
                    results.append(CheckResult(False, member, f"unsupported manifest_hash_mode: {mode!r}"))
                    continue

                canonical = canonical_manifest_bytes(manifest, mode)
                actual_hash = sha256_bytes(canonical)

                if actual_hash != expected_hash:
                    results.append(CheckResult(False, member, f"sha256 mismatch (expected {expected_hash}, got {actual_hash})"))
                    continue

                # Don't fail on bytes mismatch for manifest.json (formatting may vary)
                actual_len = len(manifest_bytes_in_zip)
                if actual_len != expected_bytes:
                    results.append(CheckResult(True, member, f"OK (bytes differ: expected {expected_bytes}, got {actual_len})"))
                else:
                    results.append(CheckResult(True, member))
                continue

            # normal members
            if member not in z.namelist():
                results.append(CheckResult(False, member, "missing from container"))
                continue

            data = read_zip_bytes(z, member)
            actual_hash = sha256_bytes(data)
            actual_len = len(data)

            if actual_len != expected_bytes:
                results.append(CheckResult(False, member, f"bytes mismatch (expected {expected_bytes}, got {actual_len})"))
                continue
            if actual_hash != expected_hash:
                results.append(CheckResult(False, member, f"sha256 mismatch (expected {expected_hash}, got {actual_hash})"))
                continue

            results.append(CheckResult(True, member))

    ok = all(r.ok for r in results)
    return ok, results


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("Usage: python3 SRC/verify_aifm.py /path/to/file.aifm [--verbose]")
        return 3

    path = Path(argv[0]).expanduser()
    verbose = "--verbose" in argv

    try:
        ok, results = verify(path)
    except Exception as e:
        print(f"ERROR: {e}")
        return 3

    print(f"File: {path}")
    print(f"Result: {'INTACT' if ok else 'TAMPERED'}\n")

    for r in results:
        if verbose or not r.ok or (r.ok and r.reason):
            status = "OK" if r.ok else "FAIL"
            line = f"[{status}] {r.path}"
            if r.reason:
                line += f" — {r.reason}"
            print(line)

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
