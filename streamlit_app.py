#!/usr/bin/env python3
"""
SLC Video Merger – Streamlit Edition
All text is rendered by Pillow (no FFmpeg drawtext = no escaping bugs).
FFmpeg only does: overlay PNG on video, normalise, concatenate.
"""

import os, subprocess, time, tempfile
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import streamlit as st

# ────────────────────────────── CONFIG ──────────────────────────────────
st.set_page_config(page_title="SLC Video Merger", page_icon="🎬", layout="wide")

BASE_DIR   = Path(__file__).parent
INTRO_TPL  = BASE_DIR / "assets" / "intro_template.mp4"

# Fonts – check bundled first, then system
def _font(name):
    candidates = [
        str(BASE_DIR / "fonts" / name),                              # bundled
        f"/usr/share/fonts/truetype/google-fonts/{name}",            # linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",     # fallback
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

BOLD   = _font("Poppins-Bold.ttf")
MEDIUM = _font("Poppins-Medium.ttf")

TEAL   = (96, 204, 190)
WHITE  = (255, 255, 255)


# ──────────────────── PILLOW: RENDER TEXT AS PNG ───────────────────────
def _ft(path, size):
    try:    return ImageFont.truetype(path, size) if path else ImageFont.load_default()
    except: return ImageFont.load_default()

def render_intro_overlay(course, unit_num, unit_title, W=1920, H=1080):
    """Return a 1920x1080 RGBA PNG with course text + turquoise badge."""
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad  = W - 200  # max text width

    # ── Course name ──
    sz = 52
    fn = _ft(BOLD, sz)
    while sz > 28:
        bb = draw.textbbox((0, 0), course, font=fn)
        if bb[2] - bb[0] <= pad: break
        sz -= 2; fn = _ft(BOLD, sz)
    bb = draw.textbbox((0, 0), course, font=fn)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    cy = 250
    draw.text(((W - tw) // 2, cy), course, fill=WHITE, font=fn)

    # ── Unit number badge ──
    ufn  = _ft(BOLD, 28)
    utxt = unit_num.upper()
    bb   = draw.textbbox((0, 0), utxt, font=ufn)
    uw   = bb[2] - bb[0]
    bw   = uw + 70
    bh   = 56                           # fixed height for consistent look
    bx   = (W - bw) // 2
    by   = cy + th + 55
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=14,
                           fill=TEAL + (230,))
    # anchor="mm" = draw centered on the midpoint of the box
    draw.text((bx + bw // 2, by + bh // 2),
              utxt, fill=WHITE, font=ufn, anchor="mm")

    # ── Unit title ──
    if unit_title and unit_title.strip():
        tsz = 30; tfn = _ft(MEDIUM, tsz)
        while tsz > 20:
            bb = draw.textbbox((0, 0), unit_title, font=tfn)
            if bb[2] - bb[0] <= pad: break
            tsz -= 2; tfn = _ft(MEDIUM, tsz)
        bb = draw.textbbox((0, 0), unit_title, font=tfn)
        ttw = bb[2] - bb[0]
        draw.text(((W - ttw) // 2, by + bh + 25), unit_title,
                  fill=WHITE, font=tfn)
    return img

def render_end_overlay(W=1920, H=1080):
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fn   = _ft(BOLD, 42)
    bb   = draw.textbbox((0, 0), "END", font=fn)
    tw   = bb[2] - bb[0]
    bw, bh = tw + 90, 72               # fixed height
    bx, by = (W - bw) // 2, (H - bh) // 2 - 20
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=16,
                           fill=TEAL + (230,))
    draw.text((bx + bw // 2, by + bh // 2),
              "END", fill=WHITE, font=fn, anchor="mm")
    return img


# ────────────────────── FFMPEG HELPERS ─────────────────────────────────
def _ff(cmd, timeout=600):
    """Run an ffmpeg command; raise on failure."""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        # grab the last meaningful lines
        err = r.stderr.strip().split("\n")
        short = "\n".join(err[-6:]) if len(err) > 6 else r.stderr
        raise RuntimeError(short)
    return r

def make_intro(course, unit_num, unit_title, tmp):
    """Overlay text PNG onto intro template with rise animation."""
    png = str(tmp / "intro_overlay.png")
    out = str(tmp / "intro.mp4")

    render_intro_overlay(course, unit_num, unit_title).save(png, "PNG")

    # Rise animation:  y = 300*(1-t/0.8)^2  for t<0.8, then y=0
    # \\, escapes commas inside FFmpeg if() expressions
    y = "if(lt(t\\,0.8)\\,300*pow(1-t/0.8\\,2)\\,0)"

    _ff([
        "ffmpeg", "-y",
        "-i", str(INTRO_TPL),
        "-loop", "1", "-i", png,
        "-filter_complex",
        "[1:v]format=rgba[ovr];[0:v][ovr]overlay=x=0:y='" + y + "':shortest=1[out]",
        "-map", "[out]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        out,
    ], timeout=60)
    return Path(out)

def make_outro(tmp):
    """Overlay END badge onto intro template with rise animation."""
    png = str(tmp / "end_overlay.png")
    out = str(tmp / "outro.mp4")

    render_end_overlay().save(png, "PNG")

    y = "if(lt(t\\,0.8)\\,250*pow(1-t/0.8\\,2)\\,0)"

    _ff([
        "ffmpeg", "-y",
        "-i", str(INTRO_TPL),
        "-loop", "1", "-i", png,
        "-filter_complex",
        "[1:v]format=rgba[ovr];[0:v][ovr]overlay=x=0:y='" + y + "':shortest=1[out]",
        "-map", "[out]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        out,
    ], timeout=60)
    return Path(out)

def normalise(inp, out):
    """Scale/pad any video to 1920x1080 @ 30fps, h264+aac."""
    _ff([
        "ffmpeg", "-y", "-i", str(inp),
        "-vf",
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black",
        "-r", "30",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        "-pix_fmt", "yuv420p",
        str(out),
    ])
    return Path(out)

def to_30fps(inp, out):
    """Re-encode to 30fps for clean concat."""
    _ff([
        "ffmpeg", "-y", "-i", str(inp),
        "-r", "30",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        "-pix_fmt", "yuv420p",
        str(out),
    ], timeout=120)
    return Path(out)

def concat(parts, out, tmp):
    """Concatenate videos via demuxer (fast copy, fallback re-encode)."""
    lst = tmp / "list.txt"
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{Path(p).resolve()}'\n")
    try:
        _ff(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(lst), "-c", "copy", str(out)])
    except RuntimeError:
        _ff(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(lst),
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p",
             str(out)])
    return Path(out)

def preview_frame(course, unit_num, unit_title):
    """Quick JPEG preview: overlay text on a still from the template."""
    tmp_path = None
    try:
        # Create temp file, close handle immediately (Windows needs this)
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)

        subprocess.run(
            ["ffmpeg", "-y", "-i", str(INTRO_TPL),
             "-ss", "3", "-vframes", "1", tmp_path],
            capture_output=True, timeout=10)

        # Load into memory then close the file
        bg = Image.open(tmp_path).convert("RGBA")
        bg.load()                       # force read into RAM
    finally:
        # Safe delete — file handle is fully released
        if tmp_path and os.path.exists(tmp_path):
            try: os.unlink(tmp_path)
            except OSError: pass

    ovr = render_intro_overlay(course, unit_num, unit_title)
    comp = Image.alpha_composite(bg, ovr).convert("RGB")
    buf = BytesIO()
    comp.save(buf, "JPEG", quality=90)
    buf.seek(0)
    return buf


# ──────────────────────── CUSTOM CSS ──────────────────────────────────
st.markdown("""<style>
.stApp{background:linear-gradient(135deg,#0a2a3c 0%,#0d3b54 30%,#0f4c6e 60%,#1a3a5c 100%)}
header[data-testid="stHeader"]{background:rgba(10,42,60,.85);backdrop-filter:blur(10px)}
section[data-testid="stSidebar"]{background:rgba(10,42,60,.95);border-right:1px solid rgba(96,204,190,.2)}
.stButton>button[kind="primary"],.stDownloadButton>button{background:#60ccbe!important;color:#0a2a3c!important;border:none!important;border-radius:12px!important;font-weight:600!important;padding:.6rem 2rem!important}
.stButton>button[kind="primary"]:hover,.stDownloadButton>button:hover{background:#4dbcad!important;box-shadow:0 4px 20px rgba(96,204,190,.3)!important}
.stTextInput>div>div>input{background:rgba(255,255,255,.08)!important;border:1px solid rgba(255,255,255,.15)!important;border-radius:10px!important;color:#fff!important}
.stTextInput>div>div>input:focus{border-color:#60ccbe!important;box-shadow:0 0 0 3px rgba(96,204,190,.15)!important}
section[data-testid="stFileUploader"]{border:2px dashed rgba(96,204,190,.4)!important;border-radius:14px!important;background:rgba(96,204,190,.03)!important}
.fb{display:inline-block;background:rgba(96,204,190,.12);border:1px solid rgba(96,204,190,.3);padding:6px 18px;border-radius:8px;font-size:14px;color:rgba(255,255,255,.85)}
.fa{display:inline-block;color:#60ccbe;font-size:18px;margin:0 6px}
.sn{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:#60ccbe;color:#0a2a3c;font-weight:700;font-size:13px;margin-right:10px}
.st{color:#60ccbe;font-size:15px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px}
.ok{text-align:center;padding:24px;background:rgba(96,204,190,.08);border:1px solid rgba(96,204,190,.25);border-radius:16px;margin:16px 0}
.ok h3{color:#60ccbe;margin-bottom:4px}
hr{border-color:rgba(96,204,190,.15)!important}
</style>""", unsafe_allow_html=True)


# ──────────────────────── LAYOUT ──────────────────────────────────────
st.markdown("""<div style="display:flex;align-items:center;gap:16px;margin-bottom:8px">
<h1 style="margin:0;font-size:28px">🎬 SLC Video Merger</h1>
<span style="background:#60ccbe;color:#0a2a3c;font-size:11px;font-weight:700;
padding:3px 12px;border-radius:20px;text-transform:uppercase">Fast</span>
</div>""", unsafe_allow_html=True)

st.markdown("""<div style="text-align:center;margin:8px 0 24px">
<span class="fb">🎬 Custom Intro</span><span class="fa">→</span>
<span class="fb">📹 NotebookLM Video</span><span class="fa">→</span>
<span class="fb">🔚 Outro</span></div>""", unsafe_allow_html=True)

# ── 1  INTRO ──
st.markdown('<div><span class="sn">1</span><span class="st">Intro Customisation</span></div>', unsafe_allow_html=True)
course_name = st.text_input("Course Name",
    placeholder="e.g. Level 3 Diploma in Sports Development (RQF)")
c1, c2 = st.columns(2)
with c1:
    unit_number = st.text_input("Unit / Chapter Number and title",
        placeholder="e.g. UNIT 03 | Anatomy and physiology for sport")


if st.button("👁  Preview Intro", type="secondary"):
    if course_name and unit_number:
        with st.spinner("Rendering…"):
            st.image(preview_frame(course_name, unit_number,  ""),
                     caption="Intro Preview", use_container_width=True)
    else:
        st.warning("Enter course name + unit number first.")

st.markdown("---")

# ── 2  UPLOAD ──
st.markdown('<div><span class="sn">2</span><span class="st">Upload NotebookLM Video</span></div>', unsafe_allow_html=True)
vid = st.file_uploader("Upload your NotebookLM video",
    type=["mp4","mov","webm","avi","mkv"],
    help="MP4 / MOV / WebM — up to 500 MB")
if vid:
    st.success(f"📁 **{vid.name}** — {vid.size / 1048576:.1f} MB")

st.markdown("---")

# ── 3  MERGE ──
st.markdown('<div><span class="sn">3</span><span class="st">Generate Final Video</span></div>', unsafe_allow_html=True)
st.markdown('<p style="font-size:13px;color:rgba(255,255,255,.5);margin-bottom:16px">'
            'Merges custom intro + uploaded video + standard outro.</p>',
            unsafe_allow_html=True)

if st.button("🎬  Merge & Download", type="primary", use_container_width=True):
    # validate
    if not course_name: st.error("Enter a course name."); st.stop()
    if not unit_number:  st.error("Enter a unit number and title.");  st.stop()
    if not vid:          st.error("Upload a video.");        st.stop()

    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bar = st.progress(0, "Starting…")
        msg = st.empty()

        try:
            # 1
            msg.info("⏳ **Step 1 / 4** — Generating custom intro…")
            bar.progress(10, "Generating intro…")
            intro = make_intro(course_name, unit_number, "", tmp)

            # 2
            msg.info("⏳ **Step 2 / 4** — Creating outro…")
            bar.progress(25, "Creating outro…")
            outro = make_outro(tmp)

            # 3
            msg.info("⏳ **Step 3 / 4** — Normalising uploaded video…")
            bar.progress(40, "Normalising…")
            raw = tmp / "raw.mp4"
            raw.write_bytes(vid.getvalue())
            norm = normalise(raw, tmp / "norm.mp4")

            intro30 = to_30fps(intro, tmp / "intro30.mp4")
            outro30 = to_30fps(outro, tmp / "outro30.mp4")
            bar.progress(70, "Merging…")

            # 4
            msg.info("⏳ **Step 4 / 4** — Merging segments…")
            final = concat([intro30, norm, outro30], tmp / "final.mp4", tmp)
            bar.progress(100, "Done!")

            secs = time.time() - t0
            data = final.read_bytes()
            mb   = len(data) / 1048576

            msg.empty(); bar.empty()

            st.markdown(f"""<div class="ok">
            <div style="font-size:48px;margin-bottom:8px">✅</div>
            <h3>Video Ready!</h3>
            <p style="color:rgba(255,255,255,.5);font-size:13px">
            Processed in {secs:.1f}s &nbsp;•&nbsp; {mb:.1f} MB</p>
            </div>""", unsafe_allow_html=True)

            safec = course_name[:30].replace(" ", "_")
            safeu = unit_number.replace(" ", "_").replace("|", "")
            st.download_button("⬇  Download Final Video", data,
                f"SLC_Video_{safec}_{safeu}.mp4", "video/mp4",
                use_container_width=True)

        except Exception as e:
            bar.empty(); msg.empty()
            st.error(f"**Processing failed:**\n\n```\n{e}\n```")
