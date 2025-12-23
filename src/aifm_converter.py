#!/usr/bin/env python3
"""
AIFM Converter (AIFX Converter v0.1 - aligned)
- Packages audio (+ optional stems, prompts, lyrics, persona, declaration) into .aifm
- Preserves payload bytes unchanged (copied into container)
- Generates metadata/manifest.json
- Generates verification/checksums.sha256 for ALL files under payload/ only (v0.1 rule)
- Adds optional public attestation URLs (--url repeatable)
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import posixpath
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


AIFX_SPEC_VERSION = "0.1"
AIFX_FORMAT_VERSION = "1.0"  # stable container/manifest format version


DEFAULT_TIER = "SDA"
DEFAULT_MODE = "human-directed-ai"


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_zip_path(*parts: str) -> str:
    # Ensure forward slashes inside zip, no leading slash
    return posixpath.normpath(posixpath.join(*parts)).lstrip("/")


def iter_files_recursive(root: Path) -> Iterable[Path]:
    for p in sorted(root.rglob("*")):
        if p.is_file():
            yield p


@dataclass
class ConvertOptions:
    audio_path: Path
    out_path: Path
    title: str
    description: str
    creation_mode: str
    tier: str
    author: str
    contact: str
    ownership_claim: bool
    ai_systems: List[str]
    apps: List[str]
    toolchain_notes: str
    prompt_path: Optional[Path]
    negative_prompt_path: Optional[Path]
    lyrics_path: Optional[Path]
    stems_dir: Optional[Path]
    persona_path: Optional[Path]
    declaration_path: Optional[Path]
    urls: List[str]


def build_manifest(opts: ConvertOptions) -> Dict:
    """
    v0.1 minimum manifest aligned with your draft, updated:
    - uses aifx_format_version + aifx_spec_version
    - uses "declaration" instead of "license"
    - references persona/declaration if present
    - includes optional public_attestation.urls
    """
    manifest: Dict = {
        "aifx_format_version": AIFX_FORMAT_VERSION,
        "aifx_spec_version": AIFX_SPEC_VERSION,
        "format": "AIFM",
        "created_at": utc_now_iso(),
        "title": opts.title or "Untitled",
        "description": opts.description or "",
        "creation_mode": opts.creation_mode,

        "human_authorship": {
            "name": opts.author,
            "role": "AI Content Director",
            "ownership_claim": bool(opts.ownership_claim),
            "contact": opts.contact,
        },

        "ai_systems": [{"name": n, "role": "generation"} for n in opts.ai_systems] if opts.ai_systems else [],

        "toolchain": {
            "apps": opts.apps if opts.apps else [],
            "notes": opts.toolchain_notes or "",
        },

        "inputs": {
            "prompts_included": bool(opts.prompt_path or opts.negative_prompt_path),
            "seeds_included": False,
            "source_assets_included": False,
        },

        "verification": {
            "tier": opts.tier,
            "method": "self-declared" if opts.tier == "SDA" else "declared",
            "signing": "none",
        },

        "integrity": {
            "hash_alg": "SHA-256",
            "checksums_ref": "verification/checksums.sha256",
        },
    }

    # Optional references
    if opts.persona_path:
        manifest["persona_ref"] = "metadata/persona.txt"

    if opts.declaration_path:
        manifest["declaration"] = {
            "type": "Creator-Declared",
            "text_ref": "metadata/declaration.txt",
        }

    # Optional content refs
    if opts.lyrics_path:
        manifest["lyrics_ref"] = "metadata/lyrics.txt"

    # Prompt refs if included
    if opts.prompt_path or opts.negative_prompt_path:
        manifest["prompt_refs"] = {
            "prompt": "metadata/prompt/prompt.txt" if opts.prompt_path else "",
            "negative_prompt": "metadata/prompt/negative_prompt.txt" if opts.negative_prompt_path else "",
        }

    # Stems indicator
    manifest["stems_included"] = bool(opts.stems_dir)

    # Public attestation URLs (optional)
    if opts.urls:
        manifest["public_attestation"] = {
            "urls": opts.urls,
            "notes": ""
        }

    return manifest


def zip_write_bytes(zf: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(arcname)
    # Deterministic timestamps for stable archives
    info.date_time = (1980, 1, 1, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, data)


def zip_write_file(zf: zipfile.ZipFile, arcname: str, src_path: Path) -> None:
    # Compression does not alter extracted bytes; payload remains unchanged.
    info = zipfile.ZipInfo(arcname)
    info.date_time = (1980, 1, 1, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    with src_path.open("rb") as f:
        zf.writestr(info, f.read())


def make_checksums_payload_only(payload_entries: List[Tuple[str, Path]]) -> str:
    """
    payload_entries: list of (zip_path, local_path) for files under payload/
    Output format: "<hex>  <zip_path>\n"
    """
    lines: List[str] = []
    for zip_path, local_path in sorted(payload_entries, key=lambda x: x[0]):
        digest = sha256_file(local_path)
        lines.append(f"{digest}  {zip_path}")
    return "\n".join(lines) + "\n"


def build_readme(manifest: Dict) -> str:
    tier = manifest.get("verification", {}).get("tier", "SDA")
    title = manifest.get("title", "Untitled")
    created_at = manifest.get("created_at", "")
    return (
        "AIFX Container (AIFM)\n"
        "-------------------\n"
        f"Title: {title}\n"
        f"Created At (UTC): {created_at}\n"
        f"Verification Tier: {tier}\n\n"
        "This container is a ZIP-based AIFX format.\n"
        "Authoritative metadata is in: metadata/manifest.json\n"
        "Integrity hashes are in: verification/checksums.sha256\n"
        "This README is non-authoritative.\n"
    )


def convert_aifm(opts: ConvertOptions) -> None:
    audio = opts.audio_path
    if not audio.exists() or not audio.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio}")

    if opts.stems_dir and not opts.stems_dir.exists():
        raise FileNotFoundError(f"Stems directory not found: {opts.stems_dir}")

    if opts.persona_path and not opts.persona_path.exists():
        raise FileNotFoundError(f"Persona file not found: {opts.persona_path}")

    if opts.declaration_path and not opts.declaration_path.exists():
        raise FileNotFoundError(f"Declaration file not found: {opts.declaration_path}")

    if opts.prompt_path and not opts.prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {opts.prompt_path}")

    if opts.negative_prompt_path and not opts.negative_prompt_path.exists():
        raise FileNotFoundError(f"Negative prompt file not found: {opts.negative_prompt_path}")

    if opts.lyrics_path and not opts.lyrics_path.exists():
        raise FileNotFoundError(f"Lyrics file not found: {opts.lyrics_path}")

    out = opts.out_path
    if out.suffix.lower() != ".aifm":
        out = out.with_suffix(".aifm")

    # Payload entries for checksum generation (payload-only)
    payload_entries: List[Tuple[str, Path]] = []

    # Canonical primary asset path
    audio_ext = audio.suffix.lower().lstrip(".") or "wav"
    audio_zip_path = normalize_zip_path("payload", "audio", f"main.{audio_ext}")
    payload_entries.append((audio_zip_path, audio))

    # Optional stems
    stems_files: List[Tuple[str, Path]] = []
    if opts.stems_dir:
        for f in iter_files_recursive(opts.stems_dir):
            rel = f.relative_to(opts.stems_dir)
            zip_path = normalize_zip_path("payload", "stems", str(rel).replace(os.sep, "/"))
            stems_files.append((zip_path, f))
        payload_entries.extend(stems_files)

    manifest = build_manifest(opts)
    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
    checksums_bytes = make_checksums_payload_only(payload_entries).encode("utf-8")
    readme_bytes = build_readme(manifest).encode("utf-8")

    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # payload
        zip_write_file(zf, audio_zip_path, audio)
        for zip_path, fpath in sorted(stems_files, key=lambda x: x[0]):
            zip_write_file(zf, zip_path, fpath)

        # metadata
        zip_write_bytes(zf, normalize_zip_path("metadata", "manifest.json"), manifest_bytes)

        if opts.prompt_path:
            zip_write_file(zf, normalize_zip_path("metadata", "prompt", "prompt.txt"), opts.prompt_path)
        if opts.negative_prompt_path:
            zip_write_file(zf, normalize_zip_path("metadata", "prompt", "negative_prompt.txt"), opts.negative_prompt_path)

        if opts.lyrics_path:
            zip_write_file(zf, normalize_zip_path("metadata", "lyrics.txt"), opts.lyrics_path)

        if opts.persona_path:
            zip_write_file(zf, normalize_zip_path("metadata", "persona.txt"), opts.persona_path)

        if opts.declaration_path:
            zip_write_file(zf, normalize_zip_path("metadata", "declaration.txt"), opts.declaration_path)

        # verification
        zip_write_bytes(zf, normalize_zip_path("verification", "checksums.sha256"), checksums_bytes)

        # README
        zip_write_bytes(zf, "README.txt", readme_bytes)

    print(f"✅ Created: {out}")
    print(f"   - Primary audio: {audio_zip_path}")
    if opts.stems_dir:
        print(f"   - Stems: {len(stems_files)} file(s)")
    if opts.persona_path:
        print("   - Persona: metadata/persona.txt")
    if opts.declaration_path:
        print("   - Declaration: metadata/declaration.txt")
    if opts.prompt_path or opts.negative_prompt_path:
        print("   - Prompt(s): metadata/prompt/")
    if opts.urls:
        print(f"   - URL(s): {len(opts.urls)}")
    print("   - Manifest: metadata/manifest.json")
    print("   - Checksums: verification/checksums.sha256")


def parse_args(argv: Optional[List[str]] = None) -> ConvertOptions:
    p = argparse.ArgumentParser(
        prog="aifm_converter.py",
        description="Convert audio into an AIFM (.aifm) container (AIFX Converter v0.1).",
    )

    p.add_argument("audio", type=str, help="Path to audio file (.wav/.mp3/etc).")
    p.add_argument("--out", type=str, required=True, help="Output .aifm path.")

    p.add_argument("--title", type=str, default="Untitled")
    p.add_argument("--desc", type=str, default="")

    p.add_argument("--mode", type=str, default=DEFAULT_MODE,
                   choices=["human-directed-ai", "ai-assisted-human", "autonomous-ai"])
    p.add_argument("--tier", type=str, default=DEFAULT_TIER, choices=["SDA", "VC", "PVA"])

    p.add_argument("--author", type=str, default="")
    p.add_argument("--contact", type=str, default="")
    p.add_argument("--no-ownership-claim", action="store_true",
                   help="Set ownership_claim=false in manifest.")

    p.add_argument("--ai-system", action="append", default=[],
                   help='AI system/model name (repeatable). e.g. --ai-system "Suno"')
    p.add_argument("--app", action="append", default=[],
                   help='Toolchain app (repeatable). e.g. --app "DaVinci Resolve"')
    p.add_argument("--toolchain-notes", type=str, default="")

    p.add_argument("--prompt", type=str, default=None, help="Path to prompt.txt")
    p.add_argument("--negative-prompt", type=str, default=None, help="Path to negative_prompt.txt")
    p.add_argument("--lyrics", type=str, default=None, help="Path to lyrics.txt")

    p.add_argument("--stems", type=str, default=None, help="Directory containing stem files (optional).")

    # Optional metadata files
    p.add_argument("--persona", type=str, default=None, help="Path to persona.txt (optional).")
    p.add_argument("--declaration", type=str, default=None, help="Path to declaration.txt (optional).")

    # Optional public URLs (repeatable)
    p.add_argument(
        "--url",
        action="append",
        default=[],
        help="Public URL where this work is posted (YouTube, SoundCloud, etc). Repeatable."
    )

    a = p.parse_args(argv)

    return ConvertOptions(
        audio_path=Path(a.audio).expanduser().resolve(),
        out_path=Path(a.out).expanduser().resolve(),
        title=a.title,
        description=a.desc,
        creation_mode=a.mode,
        tier=a.tier,
        author=a.author,
        contact=a.contact,
        ownership_claim=not a.no_ownership_claim,
        ai_systems=a.ai_system or [],
        apps=a.app or [],
        toolchain_notes=a.toolchain_notes,
        prompt_path=Path(a.prompt).expanduser().resolve() if a.prompt else None,
        negative_prompt_path=Path(a.negative_prompt).expanduser().resolve() if a.negative_prompt else None,
        lyrics_path=Path(a.lyrics).expanduser().resolve() if a.lyrics else None,
        stems_dir=Path(a.stems).expanduser().resolve() if a.stems else None,
        persona_path=Path(a.persona).expanduser().resolve() if a.persona else None,
        declaration_path=Path(a.declaration).expanduser().resolve() if a.declaration else None,
        urls=a.url or [],
    )


def main(argv: Optional[List[str]] = None) -> int:
    try:
        opts = parse_args(argv)
        convert_aifm(opts)
        return 0
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
