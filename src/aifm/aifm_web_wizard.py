#!/usr/bin/env python3
"""
AIFX Local Web Wizard — AIFM (Portable)

Origin requirements enforced in UI + server:
- Origin URL (required)
- AI Origin Platform (required dropdown + Other)
- Origin creation date (required)
- Origin time optional

Run:
  python3 SRC/aifm_web_wizard.py
Open:
  http://127.0.0.1:5055
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from zipfile import ZipFile

from flask import Flask, request, redirect, url_for, render_template_string, send_file, abort, flash

APP_HOST = "127.0.0.1"
APP_PORT = 5055

BASE_DIR = Path(__file__).resolve().parent.parent  # .../AIFM
SRC_DIR = BASE_DIR / "SRC"
CONVERTER = SRC_DIR / "aifm_converter.py"

STAGING_DIR = BASE_DIR / "_staging"
OUTPUT_DIR = BASE_DIR / "OUTPUT"

PROFILE_PATH = BASE_DIR / "_profile.json"

ALLOWED_AUDIO_EXT = {".mp3", ".wav", ".aiff", ".aif", ".flac", ".m4a"}
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}

MAX_LINK_ROWS = 5

DEFAULT_DECL_TEMPLATE = (
    "DECLARATION (AIFX / AI-First-Exchange)\n\n"
    "I, the undersigned creator, declare that this work was produced using AI tools under my direction.\n"
    "I affirm that the information in this package is accurate to the best of my knowledge.\n"
    "I understand that modifying packaged metadata may invalidate provenance and verification.\n\n"
    "Signed:\n"
    "Date:\n"
)


@dataclass
class Profile:
    author: str = ""
    contact: str = ""
    ai_system: str = "Suno"
    origin_url: str = ""
    tier: str = "SDA"
    mode: str = "human-directed-ai"


def load_profile() -> Profile:
    if PROFILE_PATH.exists():
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            base = asdict(Profile())
            if isinstance(data, dict):
                base.update(data)
            return Profile(**base)
        except Exception:
            return Profile()
    return Profile()


def save_profile(p: Profile) -> None:
    PROFILE_PATH.write_text(json.dumps(asdict(p), indent=2), encoding="utf-8")


def ensure_dirs() -> None:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r'[\/:*?"<>|]+', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name if name else "Untitled"


def validate_iso_date_yyyy_mm_dd(s: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s.strip()))


def validate_time_hh_mm_or_hh_mm_ss(s: str) -> bool:
    s = s.strip()
    if re.fullmatch(r"\d{2}:\d{2}", s):
        return True
    if re.fullmatch(r"\d{2}:\d{2}:\d{2}", s):
        return True
    return False


def read_manifest_from_aifm(aifm_path: Path) -> dict:
    with ZipFile(aifm_path, "r") as z:
        with z.open("manifest.json") as f:
            return json.loads(f.read().decode("utf-8"))


def write_temp_text_file(text: str) -> Optional[Path]:
    text = (text or "").strip()
    if not text:
        return None
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(text + "\n")
    f.flush()
    f.close()
    return Path(f.name)


def stage_upload(file_storage, dest_path: Path) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    file_storage.save(str(dest_path))
    return dest_path


app = Flask(__name__)
app.secret_key = os.urandom(16)


HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>AIFX AIFM Web Wizard</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; margin: 24px; }
    .container { max-width: 980px; margin: 0 auto; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 16px; margin-bottom: 16px; }
    label { display:block; font-weight: 600; margin-top: 12px; }
    input[type="text"], input[type="email"], input[type="url"], input[type="date"], input[type="time"], select, textarea {
      width: 100%; box-sizing: border-box; padding: 10px; border-radius: 10px; border: 1px solid #ccc;
      font-size: 14px;
    }
    textarea { min-height: 120px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .btn { display:inline-block; padding: 10px 14px; border-radius: 10px; border: 1px solid #333; background: #111; color: #fff; text-decoration:none; cursor:pointer; }
    .btn.secondary { background: #fff; color:#111; border-color:#999; }
    .muted { color:#666; font-size: 13px; }
    .hint { color:#666; font-size: 12px; margin-top:6px; }
    .flash { padding: 10px 12px; background:#fff3cd; border:1px solid #ffe69c; border-radius: 10px; margin-bottom: 12px; }
    code { background:#f5f5f5; padding: 2px 6px; border-radius: 6px; }
    .actions { display:flex; gap:10px; flex-wrap: wrap; margin-top: 12px; }
    .result { background:#f7fff7; border:1px solid #b7f0b7; }
    pre { white-space: pre-wrap; word-break: break-word; background:#f5f5f5; padding: 12px; border-radius: 10px; }
    .checkrow { display:flex; gap:10px; align-items:flex-start; margin-top:12px; }
  </style>

  <script>
    function toggleAiOther() {
      var sel = document.getElementById('ai_system_select');
      var other = document.getElementById('ai_system_other');
      if (!sel || !other) return;
      if (sel.value === 'Other') {
        other.style.display = 'block';
        other.required = true;
      } else {
        other.style.display = 'none';
        other.required = false;
        other.value = '';
      }
    }
    window.addEventListener('load', toggleAiOther);
  </script>
</head>
<body>
<div class="container">
  <h1>AIFX — AIFM Local Web Wizard</h1>
  <p class="muted">Portable folder wizard. Outputs to <code>OUTPUT/&lt;Song Title&gt;/&lt;Song Title&gt;.aifm</code>.</p>

  {% with messages = get_flashed_messages() %}
    {% if messages %}
      {% for m in messages %}
        <div class="flash">{{ m }}</div>
      {% endfor %}
    {% endif %}
  {% endwith %}

  <div class="card">
    <h2>Convert</h2>
    <form method="post" action="{{ url_for('convert') }}" enctype="multipart/form-data">
      <label>Audio file (required)</label>
      <input type="file" name="audio" accept=".mp3,.wav,.aiff,.aif,.flac,.m4a" required>
      <div class="hint">Place your sample audio anywhere (Downloads/Desktop). The wizard stages it into <code>_staging/</code>.</div>

      <label>Title (required)</label>
      <input type="text" name="title" required>

      <div class="row">
        <div>
          <label>Origin URL on AI platform (required)</label>
          <input type="url" name="origin_url" value="{{ defaults.origin_url }}" placeholder="https://suno.com/song/..." required>
          <div class="hint">Must be the AI generation platform link (Suno/Udio/ElevenLabs/etc), not a posting site.</div>
        </div>
        <div>
          <label>AI Origin Platform (required)</label>
          <select name="ai_system" id="ai_system_select" required onchange="toggleAiOther()">
            {% for opt in ["Suno","Udio","ElevenLabs","Stable Audio","AIVA","Other"] %}
              <option value="{{opt}}" {% if defaults.ai_system==opt or (opt=="Other" and defaults.ai_system not in ["Suno","Udio","ElevenLabs","Stable Audio","AIVA","Other"]) %}selected{% endif %}>{{opt}}</option>
            {% endfor %}
          </select>
          <input type="text" name="ai_system_other" id="ai_system_other"
                 value="{% if defaults.ai_system not in ['Suno','Udio','ElevenLabs','Stable Audio','AIVA','Other'] %}{{ defaults.ai_system }}{% endif %}"
                 placeholder="Type the AI platform name..." style="margin-top:8px; display:none;">
        </div>
      </div>

      <div class="row">
        <div>
          <label>Origin creation date (required)</label>
          <input type="date" name="original_date" required>
          <div class="hint">YYYY-MM-DD</div>
        </div>
        <div>
          <label>Origin creation time (optional)</label>
          <input type="time" name="original_time" step="1">
          <div class="hint">HH:MM or HH:MM:SS</div>
        </div>
      </div>

      <div class="row">
        <div>
          <label>Verification Tier</label>
          <select name="tier">
            {% for opt in ["SDA","VC","PVA"] %}
              <option value="{{opt}}" {% if defaults.tier==opt %}selected{% endif %}>{{opt}}</option>
            {% endfor %}
          </select>
          <div class="hint">SDA = self-declared (no signature yet).</div>
        </div>
        <div>
          <label>Mode</label>
          <select name="mode">
            {% for opt in ["human-directed-ai","ai-assisted-human","autonomous-ai"] %}
              <option value="{{opt}}" {% if defaults.mode==opt %}selected{% endif %}>{{opt}}</option>
            {% endfor %}
          </select>
        </div>
      </div>

      <div class="row">
        <div>
          <label>Author (required)</label>
          <input type="text" name="author" value="{{ defaults.author }}" required>
        </div>
        <div>
          <label>Contact (required)</label>
          <input type="text" name="contact" value="{{ defaults.contact }}" required>
        </div>
      </div>

      <label>Links (optional)</label>
      <div class="hint">These are distribution/reference links (YouTube, Spotify, etc). Origin must be the AI platform URL above.</div>
      {% for i in range(1, max_links+1) %}
      <div class="row">
        <div>
          <input type="text" name="link_label_{{i}}" placeholder="Label (e.g., YouTube)">
        </div>
        <div>
          <input type="url" name="link_url_{{i}}" placeholder="https://...">
        </div>
      </div>
      {% endfor %}

      <label>Prompt (optional)</label>
      <textarea name="prompt" placeholder="Paste your prompt here..."></textarea>

      <label>Persona (optional)</label>
      <textarea name="persona" placeholder="Paste persona/artist intent here..."></textarea>

      <label>Lyrics (optional)</label>
      <textarea name="lyrics" placeholder="Paste lyrics here..."></textarea>

      <label>Declaration (required)</label>
      <textarea name="declaration" required>{{ default_decl }}</textarea>

      <div class="checkrow">
        <input type="checkbox" name="decl_confirm" required>
        <div class="muted">I confirm the declaration is accurate and I understand repackaging may invalidate provenance checks.</div>
      </div>

      <label>Upload immutable declaration certificate (PDF, optional)</label>
      <input type="file" name="declaration_pdf" accept=".pdf">

      <label>Upload cover image (optional)</label>
      <input type="file" name="cover_image" accept=".png,.jpg,.jpeg,.webp">

      <div class="actions">
         <button class="btn" type="submit">Convert → .aifm</button>

         <a class="btn secondary" href="{{ url_for('index') }}">Reset</a>

         <button
            class="btn secondary"
            type="button"
            onclick="if (confirm('Exit AIFM Wizard? You can safely close this window.')) { window.close(); }"
         >
            Exit &amp; Close
       </button>
  </div>


  {% if result %}
  <div class="card result">
    <h2>Result</h2>
    <p><strong>Created:</strong> <code>{{ result.aifm_path }}</code></p>
    <p><strong>Song folder:</strong> <code>{{ result.song_dir }}</code></p>
    <p><strong>Copied original audio:</strong> <code>{{ result.copied_audio }}</code></p>

    <div class="actions">
      <a class="btn secondary" href="{{ url_for('download', job_id=result.job_id) }}">Download .aifm</a>
      <a class="btn secondary" href="{{ url_for('manifest', job_id=result.job_id) }}">View Manifest</a>
    </div>

    <h3>Converter output</h3>
    <pre>{{ result.log }}</pre>
  </div>
  {% endif %}
</div>
</body>
</html>
"""

JOBS: dict[str, dict] = {}


@app.get("/")
def index():
    ensure_dirs()
    prof = load_profile()
    return render_template_string(
        HTML,
        defaults=prof,
        result=None,
        max_links=MAX_LINK_ROWS,
        default_decl=DEFAULT_DECL_TEMPLATE,
    )


def next_job_id(aifm_path: Path) -> str:
    return sanitize_name(aifm_path.stem) + "-" + str(abs(hash(str(aifm_path))))


@app.post("/convert")
def convert():
    ensure_dirs()

    if not CONVERTER.exists():
        flash(f"Converter not found: {CONVERTER}")
        return redirect(url_for("index"))

    audio = request.files.get("audio")
    if not audio or not audio.filename:
        flash("Audio file is required.")
        return redirect(url_for("index"))

    ext = Path(audio.filename).suffix.lower()
    if ext not in ALLOWED_AUDIO_EXT:
        flash(f"Unsupported audio type: {ext}. Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXT))}")
        return redirect(url_for("index"))

    title = sanitize_name(request.form.get("title") or "")
    author = (request.form.get("author") or "").strip()
    contact = (request.form.get("contact") or "").strip()

    ai_system_sel = (request.form.get("ai_system") or "").strip()
    ai_system_other = (request.form.get("ai_system_other") or "").strip()
    ai_system = ai_system_other if ai_system_sel == "Other" else ai_system_sel

    origin_url = (request.form.get("origin_url") or "").strip()
    tier = (request.form.get("tier") or "SDA").strip()
    mode = (request.form.get("mode") or "human-directed-ai").strip()

    original_date = (request.form.get("original_date") or "").strip()
    original_time = (request.form.get("original_time") or "").strip()

    # REQUIRED origin date
    if not original_date:
        flash("Origin creation date is required.")
        return redirect(url_for("index"))
    if not validate_iso_date_yyyy_mm_dd(original_date):
        flash("Origin creation date must be a valid YYYY-MM-DD date.")
        return redirect(url_for("index"))

    # OPTIONAL time
    if original_time and not validate_time_hh_mm_or_hh_mm_ss(original_time):
        flash("Origin creation time must be HH:MM or HH:MM:SS (24-hour).")
        return redirect(url_for("index"))

    # Collect optional distribution/reference links
    links: list[tuple[str, str]] = []
    for i in range(1, MAX_LINK_ROWS + 1):
        label = (request.form.get(f"link_label_{i}") or "").strip()
        url = (request.form.get(f"link_url_{i}") or "").strip()
        if url:
            links.append((label or "Link", url))

    if not (title and author and contact and ai_system and origin_url):
        flash("Title, Author, Contact, AI Origin Platform, and Origin URL are required.")
        return redirect(url_for("index"))

    if not (origin_url.startswith("http://") or origin_url.startswith("https://")):
        flash("Origin URL must start with http:// or https://")
        return redirect(url_for("index"))

    declaration = (request.form.get("declaration") or "").strip()
    if not declaration:
        flash("Declaration is required.")
        return redirect(url_for("index"))

    if not request.form.get("decl_confirm"):
        flash("You must confirm the declaration checkbox.")
        return redirect(url_for("index"))

    prompt = request.form.get("prompt") or ""
    lyrics = request.form.get("lyrics") or ""
    persona = request.form.get("persona") or ""

    # Save profile defaults (does not store date/time)
    save_profile(Profile(author=author, contact=contact, ai_system=ai_system, origin_url=origin_url, tier=tier, mode=mode))

    # Prepare output folder
    song_dir = OUTPUT_DIR / title
    song_dir.mkdir(parents=True, exist_ok=True)

    # Stage audio
    staging_audio = STAGING_DIR / f"{title}{ext}"
    stage_upload(audio, staging_audio)

    out_aifm = song_dir / f"{title}.aifm"

    # Stage optional PDF
    decl_pdf = request.files.get("declaration_pdf")
    staging_pdf = None
    if decl_pdf and decl_pdf.filename:
        pdf_ext = Path(decl_pdf.filename).suffix.lower()
        if pdf_ext != ".pdf":
            flash("Declaration certificate must be a PDF.")
            return redirect(url_for("index"))
        staging_pdf = STAGING_DIR / f"{title}_declaration.pdf"
        stage_upload(decl_pdf, staging_pdf)

    # Stage optional cover
    cover = request.files.get("cover_image")
    staging_cover = None
    if cover and cover.filename:
        cext = Path(cover.filename).suffix.lower()
        if cext not in ALLOWED_IMAGE_EXT:
            flash("Cover must be png/jpg/jpeg/webp.")
            return redirect(url_for("index"))
        staging_cover = STAGING_DIR / f"{title}_cover{cext}"
        stage_upload(cover, staging_cover)

    tmp_files: list[Path] = []
    try:
        prompt_path = write_temp_text_file(prompt)
        lyrics_path = write_temp_text_file(lyrics)
        persona_path = write_temp_text_file(persona)

        for p in [prompt_path, lyrics_path, persona_path]:
            if p:
                tmp_files.append(p)

        decl_tmp = write_temp_text_file(declaration)
        if decl_tmp:
            tmp_files.append(decl_tmp)

        args = [
            sys.executable, str(CONVERTER),
            str(staging_audio),
            "--out", str(out_aifm),
            "--title", title,
            "--author", author,
            "--contact", contact,
            "--ai-system", ai_system,
            "--origin-platform", ai_system,
            "--origin-url", origin_url,
            "--original-date", original_date,  # REQUIRED
            "--tier", tier,
            "--mode", mode,
            "--declaration", str(decl_tmp),
        ]

        if original_time:
            args += ["--original-time", original_time]

        for label, url in links:
            args += ["--url", f"{label}|{url}"]

        if prompt_path:
            args += ["--prompt", str(prompt_path)]
        if lyrics_path:
            args += ["--lyrics", str(lyrics_path)]
        if persona_path:
            args += ["--persona", str(persona_path)]
        if staging_pdf:
            args += ["--declaration-pdf", str(staging_pdf)]
        if staging_cover:
            args += ["--cover-image", str(staging_cover)]

        proc = subprocess.run(args, capture_output=True, text=True)

        log = ""
        if proc.stdout:
            log += proc.stdout
        if proc.stderr:
            log += ("\n" if log else "") + proc.stderr

        if proc.returncode != 0:
            flash("Conversion failed. See log on page.")
            result = {
                "job_id": "failed",
                "aifm_path": str(out_aifm),
                "song_dir": str(song_dir),
                "copied_audio": "(not copied)",
                "log": log,
            }
            prof = load_profile()
            return render_template_string(
                HTML,
                defaults=prof,
                result=result,
                max_links=MAX_LINK_ROWS,
                default_decl=DEFAULT_DECL_TEMPLATE,
            )

        # Copy original audio into song dir (unchanged)
        copied_audio = song_dir / staging_audio.name
        try:
            shutil.copy2(staging_audio, copied_audio)
        except Exception as e:
            copied_audio = Path(f"(copy failed: {e})")

        job_id = next_job_id(out_aifm)
        JOBS[job_id] = {"aifm": str(out_aifm)}

        result = {
            "job_id": job_id,
            "aifm_path": str(out_aifm),
            "song_dir": str(song_dir),
            "copied_audio": str(copied_audio),
            "log": log or "Created successfully.",
        }

        prof = load_profile()
        return render_template_string(
            HTML,
            defaults=prof,
            result=result,
            max_links=MAX_LINK_ROWS,
            default_decl=DEFAULT_DECL_TEMPLATE,
        )

    finally:
        for p in tmp_files:
            try:
                p.unlink()
            except Exception:
                pass


@app.get("/download/<job_id>")
def download(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        abort(404)
    aifm = Path(job["aifm"])
    if not aifm.exists():
        abort(404)
    return send_file(aifm, as_attachment=True, download_name=aifm.name)


@app.get("/manifest/<job_id>")
def manifest(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        abort(404)
    aifm = Path(job["aifm"])
    if not aifm.exists():
        abort(404)

    try:
        data = read_manifest_from_aifm(aifm)
    except Exception as e:
        return f"<pre>Could not read manifest: {e}</pre>", 500

    return f"<pre>{json.dumps(data, indent=2, ensure_ascii=False)}</pre>"


def main() -> None:
    ensure_dirs()
    print(f"AIFM Web Wizard running at http://{APP_HOST}:{APP_PORT}")
    print(f"Base dir: {BASE_DIR}")
    app.run(host=APP_HOST, port=APP_PORT, debug=True)


if __name__ == "__main__":
    main()
