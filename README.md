# aifx-reference-impl
Reference implementation of the AI First Exchange (AIFX) container formats. This repository demonstrates how AIFX containers (AIFM, AIFI, AIFV) can be created and verified. It is documentation-first, not DRM, and does not prevent copying.

AIFX Reference Implementation

AIFX Reference Implementation (v0.1)
Python tools for creating and validating AI First Exchange (AIFX) containers.

This repository provides a non-normative, documentation-first reference implementation of the AIFX container formats, starting with AIFM (AI First Music).

⚠️ This repository demonstrates one possible implementation.
It does not define the AIFX standard itself and is not DRM.

What This Is

This repository contains:

A working AIFM converter (.aifm)

A working AIFM reader / validator

Example metadata files (persona, declaration, prompts, lyrics)

A concrete demonstration of AIFX principles:

provenance

integrity

transparency

human accountability

The goal is to show how AIFX containers can be created, inspected, and verified using simple, open tooling.

What This Is Not

To avoid confusion, this implementation intentionally does not:

❌ Prevent copying or extraction of media

❌ Enforce copyright or ownership

❌ Act as DRM or content protection

❌ Verify truthfulness of claims

AIFX records claims and context, not legal judgments.

Core Concepts
AIFM (.aifm)

An AI First Music container is a ZIP-based archive that bundles:

Original audio (unchanged)

Human authorship declaration

AI tool disclosure

Optional prompts, lyrics, persona

Cryptographic integrity hashes

Optional public attestation URLs (YouTube, SoundCloud, etc.)

The .aifm file represents the creative work, not just the audio file.

Repository Structure
aifx-reference-impl/
├─ src/
│  ├─ aifm_converter.py      # Convert audio into .aifm container
│  └─ aifm_reader.py         # Inspect + verify .aifm container
├─ examples/
│  ├─ example_declaration.txt
│  ├─ example_persona.txt
│  ├─ example_prompt.txt
│  ├─ example_lyrics.txt
│  └─ README.md
├─ spec/
│  └─ AIFX_Converter_Spec_v0.1.md
├─ README.md
└─ LICENSE

Requirements

Python 3.9+

No external dependencies (standard library only)

Usage
Convert audio → AIFM
python3 src/aifm_converter.py "./song.mp3" \
  --out "./song.aifm" \
  --title "Song Title" \
  --mode human-directed-ai \
  --tier SDA \
  --author "Creator Name" \
  --contact "email@example.com" \
  --ai-system "Suno" \
  --prompt "./prompt.txt" \
  --lyrics "./lyrics.txt" \
  --persona "./persona.txt" \
  --declaration "./declaration.txt" \
  --url "https://www.youtube.com/watch?v=XXXXX"

Read & verify an AIFM container
python3 src/aifm_reader.py "./song.aifm"


This will:

Display the manifest (authoritative)

Display persona & declaration (non-authoritative)

Show public attestation URLs (if present)

Verify payload integrity using SHA-256

View metadata without extracting
unzip -p "./song.aifm" metadata/lyrics.txt

Integrity Model

Only files under payload/ are hashed

Metadata is intentionally not hashed

Any modification to the payload invalidates verification

Repackaging creates a new claim with a new timestamp

This design favors auditability over enforcement.

Security & Trust Model

AIFX uses layered credibility, not technical lock-in:

Cryptographic integrity (checksums)

Explicit authorship declaration

Identity disclosure (email/contact)

Public attestation URLs

Timeline & platform corroboration

This mirrors how trust works in real-world publishing systems.

Relationship to the AIFX Specification

This repository is non-normative

The AIFX specification lives in a separate repository

Future implementations may differ in language, structure, or features

Do not treat this code as the standard itself.

License

This repository is licensed under the MIT License.

The AIFX format specification and related standards are governed separately.

Status & Roadmap
Current (v0.1)

AIFM conversion

Manifest generation

SHA-256 integrity checks

Reader/validator

Planned

AIFI (images)

AIFV (video)

Optional signing

Identity attestation extensions

Deterministic packaging

Additional language implementations

Contributing

Contributions are welcome, especially:

Bug fixes

Documentation improvements

Additional reference tools

Cross-language ports

Please keep changes aligned with the AIFX philosophy:

documentation-first, transparent, non-DRM.

Final Note

AIFX is about preserving truth, not enforcing control.

This reference implementation exists to make that idea tangible.
