#!/usr/bin/env python3
"""
AI-First-Exchange (AIFX)
AIFM Converter — Reference Implementation (v0.3)

Enforces REQUIRED:
- --origin-platform
- --origin-url
- --original-date
- --ai-system
- --declaration

Hashes EVERYTHING written into the .aifm, including:
- payload/audio.*
- metadata/*.txt
- metadata/declaration.pdf (optional)
- metadata/cover.* (optional)
- manifest.json (canonical self-hash mode)

Manifest self-hash mode:
- integrity.hashed_files["manifest.json"] is computed from canonical manifest JSON
  where the manifest.json hash entry is omitted (to avoid circular dependency).
- integrity.manifest_hash_mode = "canonical_excludes_self"
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


FORMAT_NAME = "AIFM"
FORMAT_VERSION = "0.3"

AIFX_GOVERNANCE = {
    "standard": "AI-First-Exchange",
    "repo": "https://github.com/ai-first-exchange",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_valid_date_yyyy_mm_dd(s: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", (s or "").strip()))


def is_valid_time_hh_mm_or_hh_mm_ss(s: str) -> bool:
    s = (s or "").strip()
    if not s:
        return False
    return bool(re.fullmatch(r"\d{2}:\d{2}(:\d{2})?", s))


def sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    return p.read_text(encoding="utf-8", errors="replace")


def _txt_bytes(text: str) -> bytes:
    # Normalize text file bytes deterministically: UTF-8 + trailing newline.
    return (text.strip() + "\n").encode("utf-8")


def _add_hashed_bytes(integrity: dict, zip_path: str, data: bytes) -> None:
    integrity[zip_path] = {
        "sha256": sha256_bytes(data),
        "bytes": len(data),
    }


def build_aifm(
    audio_path: Path,
    out_path: Path,
    title: str,
    author: str,
    contact: str,
    ai_system: str,
    tier: str,
    mode: str,
    origin_platform: str,
    origin_url: str,
    original_date: str,
    original_time: str | None = None,
    urls: list[str] | None = None,
    cover_image_path: Path | None = None,
    prompt: str | None = None,
    lyrics: str | None = None,
    persona: str | None = None,
    declaration: str | None = None,
    declaration_pdf_path: Path | None = None,
) -> Path:
    audio_path = audio_path.resolve()
    out_path = out_path.resolve()

    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    # REQUIRED origin + date
    origin_platform = (origin_platform or "").strip()
    origin_url = (origin_url or "").strip()
    original_date = (original_date or "").strip()
    original_time = (original_time or "").strip() if original_time else None

    if not origin_platform:
        raise ValueError("origin_platform is required")
    if not (origin_url.startswith("http://") or origin_url.startswith("https://")):
        raise ValueError("origin_url must start with http:// or https://")
    if not is_valid_date_yyyy_mm_dd(original_date):
        raise ValueError("original_date must be YYYY-MM-DD (required)")
    if original_time and not is_valid_time_hh_mm_or_hh_mm_ss(original_time):
        raise ValueError("original_time must be HH:MM or HH:MM:SS (optional)")

    # Declaration required
    if not (declaration or "").strip():
        raise ValueError("declaration text is required")

    # Optional PDF
    if declaration_pdf_path is not None:
        declaration_pdf_path = declaration_pdf_path.resolve()
        if not declaration_pdf_path.exists():
            raise FileNotFoundError(declaration_pdf_path)
        if declaration_pdf_path.suffix.lower() != ".pdf":
            raise ValueError("declaration_pdf_path must be a .pdf file")

    # Optional cover image validation
    if cover_image_path is not None:
        cover_image_path = cover_image_path.resolve()
        if not cover_image_path.exists():
            raise FileNotFoundError(cover_image_path)
        if cover_image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("cover_image_path must be .png, .jpg, .jpeg, or .webp")

    urls = urls or []
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ext = audio_path.suffix.lower().lstrip(".") or "bin"
    payload_name = f"payload/audio.{ext}"

    mime = mimetypes.guess_type(str(audio_path))[0] or "application/octet-stream"

    # ---------------- Integrity (hash everything) ----------------
    integrity_hashes: dict[str, dict] = {}

    # Hash payload audio
    integrity_hashes[payload_name] = {
        "sha256": sha256_file(audio_path),
        "bytes": audio_path.stat().st_size,
    }

    # Prepare metadata text bytes (deterministic) and hash them
    prompt_zip = "metadata/prompt.txt" if prompt and prompt.strip() else None
    lyrics_zip = "metadata/lyrics.txt" if lyrics and lyrics.strip() else None
    persona_zip = "metadata/persona.txt" if persona and persona.strip() else None

    decl_zip = "metadata/declaration.txt"
    decl_bytes = _txt_bytes(declaration)

    _add_hashed_bytes(integrity_hashes, decl_zip, decl_bytes)

    prompt_bytes = _txt_bytes(prompt) if prompt_zip else None
    lyrics_bytes = _txt_bytes(lyrics) if lyrics_zip else None
    persona_bytes = _txt_bytes(persona) if persona_zip else None

    if prompt_zip and prompt_bytes is not None:
        _add_hashed_bytes(integrity_hashes, prompt_zip, prompt_bytes)
    if lyrics_zip and lyrics_bytes is not None:
        _add_hashed_bytes(integrity_hashes, lyrics_zip, lyrics_bytes)
    if persona_zip and persona_bytes is not None:
        _add_hashed_bytes(integrity_hashes, persona_zip, persona_bytes)

    # Optional immutable PDF hashed
    pdf_zip_path = None
    if declaration_pdf_path:
        pdf_zip_path = "metadata/declaration.pdf"
        integrity_hashes[pdf_zip_path] = {
            "sha256": sha256_file(declaration_pdf_path),
            "bytes": declaration_pdf_path.stat().st_size,
        }

    # Optional cover hashed
    cover_zip_path = None
    if cover_image_path is not None:
        cover_zip_path = f"metadata/cover{cover_image_path.suffix.lower()}"
        integrity_hashes[cover_zip_path] = {
            "sha256": sha256_file(cover_image_path),
            "bytes": cover_image_path.stat().st_size,
        }

    # ---------------- Manifest (before self-hash) ----------------
    manifest: dict = {
        "aifx": {
            "governance": AIFX_GOVERNANCE,
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
        },
        "created_utc": utc_now(),
        "origin": {
            "ai_platform": origin_platform,
            "primary_url": origin_url,
            "generated_date": original_date,      # REQUIRED
            "generated_time": original_time,      # OPTIONAL
        },
        "work": {"title": title, "type": "music"},
        "creator": {"name": author, "contact": contact},
        "ai": {"system": ai_system},
        "mode": mode,
        "verification": {"tier": tier},
        "payload": {
            "primary": payload_name,
            "mime": mime,
        },
        "links": [],
        "metadata_refs": {
            "declaration_text": decl_zip,
        },
        "integrity": {
            "algorithm": "sha256",
            "hashed_files": integrity_hashes,
            "manifest_hash_mode": "canonical_excludes_self",
        },
    }

    # Metadata refs
    if prompt_zip:
        manifest["metadata_refs"]["prompt"] = prompt_zip
    if lyrics_zip:
        manifest["metadata_refs"]["lyrics"] = lyrics_zip
    if persona_zip:
        manifest["metadata_refs"]["persona"] = persona_zip
    if pdf_zip_path:
        manifest["metadata_refs"]["declaration_pdf"] = pdf_zip_path
    if cover_zip_path:
        manifest["metadata_refs"]["cover_image"] = cover_zip_path

    # Optional links (distribution/reference)
    for item in urls:
        s = (item or "").strip()
        if not s:
            continue
        label, link = ("Link", s)
        if "|" in s:
            parts = s.split("|", 1)
            label = parts[0].strip() or "Link"
            link = parts[1].strip()
        manifest["links"].append({"label": label, "url": link})

    # ---------------- Manifest self-hash (canonical) ----------------
    # Canonical rule: compute hash of manifest JSON where the manifest.json entry is NOT present.
    canonical_manifest = json.loads(json.dumps(manifest))  # deep-ish copy via JSON
    canonical_manifest["integrity"]["hashed_files"].pop("manifest.json", None)

    canonical_bytes = json.dumps(canonical_manifest, indent=2, ensure_ascii=False).encode("utf-8")
    manifest_self_hash = sha256_bytes(canonical_bytes)

    # Store as integrity for manifest.json
    integrity_hashes["manifest.json"] = {
        "sha256": manifest_self_hash,
        "bytes": len(json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")),  # final bytes length
    }

    # Now serialize final manifest
    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")

    # Update manifest.json bytes length accurately
    integrity_hashes["manifest.json"]["bytes"] = len(manifest_bytes)

    # ---------------- Write ZIP ----------------
    with ZipFile(out_path, "w", ZIP_DEFLATED) as z:
        # payload
        z.write(audio_path, payload_name)

        # metadata texts
        z.writestr(decl_zip, decl_bytes)
        if prompt_zip and prompt_bytes is not None:
            z.writestr(prompt_zip, prompt_bytes)
        if lyrics_zip and lyrics_bytes is not None:
            z.writestr(lyrics_zip, lyrics_bytes)
        if persona_zip and persona_bytes is not None:
            z.writestr(persona_zip, persona_bytes)

        # optional pdf/cover
        if declaration_pdf_path:
            z.write(declaration_pdf_path, pdf_zip_path)
        if cover_image_path is not None:
            z.write(cover_image_path, cover_zip_path)

        # manifest last (fine either way)
        z.writestr("manifest.json", manifest_bytes)

    return out_path


def parse_args(argv):
    p = argparse.ArgumentParser(description="AIFX AIFM Converter (hash everything)")
    p.add_argument("audio", help="Path to audio file (wav/mp3/etc)")
    p.add_argument("--out", required=True, help="Output .aifm path")
    p.add_argument("--title", required=True)
    p.add_argument("--author", required=True)
    p.add_argument("--contact", required=True)

    # Required origin layer
    p.add_argument("--origin-platform", required=True, help="AI generation platform (e.g., Suno, Udio)")
    p.add_argument("--origin-url", required=True, help="Direct AI platform link for this work")

    # Required origin date (time optional)
    p.add_argument("--original-date", required=True, help="Origin creation date YYYY-MM-DD (required)")
    p.add_argument("--original-time", help="Origin creation time HH:MM or HH:MM:SS (optional)")

    # Keep ai-system required (can match origin-platform, but not forced)
    p.add_argument("--ai-system", required=True)

    p.add_argument("--tier", default="SDA")
    p.add_argument("--mode", default="human-directed-ai")

    p.add_argument("--prompt")
    p.add_argument("--lyrics")
    p.add_argument("--persona")
    p.add_argument("--declaration", required=True)
    p.add_argument("--declaration-pdf", dest="declaration_pdf")

    p.add_argument("--cover-image", help="Optional cover image file (png/jpg/webp)")
    p.add_argument(
        "--url",
        action="append",
        default=[],
        help="Optional URL(s). Use 'Label|https://...' format. Can be repeated.",
    )

    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    pdf_path = Path(args.declaration_pdf) if args.declaration_pdf else None

    out = build_aifm(
        audio_path=Path(args.audio),
        out_path=Path(args.out),
        title=args.title,
        author=args.author,
        contact=args.contact,
        ai_system=args.ai_system,
        tier=args.tier,
        mode=args.mode,
        origin_platform=args.origin_platform,
        origin_url=args.origin_url,
        original_date=args.original_date,
        original_time=args.original_time,
        urls=args.url,
        cover_image_path=Path(args.cover_image).resolve() if args.cover_image else None,
        prompt=read_text(args.prompt),
        lyrics=read_text(args.lyrics),
        persona=read_text(args.persona),
        declaration=read_text(args.declaration),
        declaration_pdf_path=pdf_path,
    )

    # ASCII-safe print (avoid Windows cp1252 UnicodeEncodeError)
    print(f"AIFM created: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
