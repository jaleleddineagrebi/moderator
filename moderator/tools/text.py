"""Fonts, Arabic-aware text drawing for Pillow, and ASS caption files for ffmpeg/libass."""

from __future__ import annotations

from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import ImageDraw, ImageFont

from .. import ROOT

FONTS_DIR = ROOT / "library" / "fonts"
FONT_FILES = {"ar": "NotoSansArabic-Black.ttf", "en": "NotoSans-Black.ttf", "fr": "NotoSans-Black.ttf"}
# Family names as libass sees them in FONTS_DIR
ASS_FONTS = {"ar": "Noto Sans Arabic Black", "en": "Noto Sans Black", "fr": "Noto Sans Black"}
RTL = {"ar"}


def escape_filter_arg(value: str) -> str:
    """Escape a file or directory path for ffmpeg filter option values (e.g. subtitles=..., fontsdir=...)."""
    out = value.replace("\\", "/")
    for ch in (":", "'", "[", "]", ",", ";"):
        out = out.replace(ch, f"\\{ch}")
    return out


def font(lang: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / FONT_FILES.get(lang, FONT_FILES["fr"])), size)


def visual(text: str, lang: str) -> str:
    """Pillow has no Arabic shaping here (no libraqm), so join letters and reorder right-to-left first."""
    if lang not in RTL:
        return text
    text = text.replace("\u2026", "...")  # Noto Sans Arabic has no ellipsis glyph
    return get_display(arabic_reshaper.reshape(text))


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def draw_block(img, text: str, lang: str, *, size: int, y_center: int, max_width: int,
               fill=(255, 255, 255), stroke=(0, 0, 0), stroke_width: int = 10) -> None:
    draw = ImageDraw.Draw(img)
    fnt = font(lang, size)
    lines = wrap(draw, text, fnt, max_width)  # wrap in logical order, then shape each line
    line_h = int(size * 1.25)
    y = y_center - line_h * len(lines) // 2
    for line in lines:
        shown = visual(line, lang)
        w = draw.textlength(shown, font=fnt)
        draw.text(((img.width - w) / 2, y), shown, font=fnt, fill=fill, stroke_width=stroke_width, stroke_fill=stroke)
        y += line_h


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


_STOPWORDS = {
    "the", "and", "for", "you", "your", "are", "with", "that", "this", "from", "into", "have", "has", "had",
    "was", "were", "will", "can", "but", "not", "what", "when", "why", "how", "who", "all", "its", "out",
    "les", "des", "une", "dans", "pour", "sur", "que", "qui", "pas", "plus", "avec", "ton", "tes", "son", "ses",
}


def _best_power_word_idx(tokens: list[str], lang: str) -> int:
    if lang in RTL or len(tokens) < 2:
        return -1
    best_idx = -1
    best_score = -1
    for idx, tok in enumerate(tokens):
        clean = tok.strip(".,?!:;\"'()-—").lower()
        if not clean:
            continue
        if any(ch.isdigit() for ch in clean):
            score = 100 + len(clean)
        elif clean not in _STOPWORDS and len(clean) >= 4:
            score = len(clean)
        else:
            score = 0
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx if best_score >= 4 else -1


def highlight_power_word(raw_text: str, lang: str) -> str:
    """Highlight the single most impactful word in a 2-3 word caption chunk in Cyber Yellow (&H0000E5FF)."""
    escaped = _ass_escape(raw_text)
    tokens = escaped.split()
    best_idx = _best_power_word_idx(tokens, lang)
    if best_idx >= 0:
        tokens[best_idx] = f"{{\\c&H0000E5FF&}}{tokens[best_idx]}{{\\c&H00FFFFFF&}}"
    return " ".join(tokens)


def write_caption_overlay_track(run_dir: Path, lang: str, captions: list[dict], headlines: list[dict],
                                total: float, size: tuple[int, int] = (1080, 1920)) -> str:
    """Fallback when ffmpeg lacks libass (`subtitles` filter, e.g. macOS Homebrew ffmpeg@9):
    renders each unique (headline, caption) state as a transparent RGBA PNG with Pillow and writes
    an ffconcat timeline file relative to `run_dir`."""
    from PIL import Image

    res_x, res_y = size
    is_landscape = res_x > res_y
    cap_size = 76 if is_landscape else 108
    head_size = 56 if is_landscape else 76
    cap_y = res_y - (165 if is_landscape else 620)
    head_y = 95 if is_landscape else 270
    max_w = res_x - 140

    frames_dir = run_dir / f"cap_frames_{lang}"
    frames_dir.mkdir(parents=True, exist_ok=True)
    cap_fnt = font(lang, cap_size)

    raw_pts = {0.0, round(max(total, 0.1), 3)}
    for item in (*captions, *headlines):
        raw_pts.add(round(min(max(float(item["start"]), 0.0), total), 3))
        raw_pts.add(round(min(max(float(item["end"]), 0.0), total), 3))
    pts = sorted(raw_pts)
    filtered_pts = [pts[0]]
    for p in pts[1:]:
        if p - filtered_pts[-1] >= 0.02:
            filtered_pts.append(p)
    if len(filtered_pts) < 2:
        filtered_pts = [0.0, round(max(total, 0.1), 3)]

    state_cache: dict[tuple[str, str], str] = {}

    def render_state(h_txt: str, c_txt: str) -> str:
        key = (h_txt, c_txt)
        if key in state_cache:
            return state_cache[key]
        idx = len(state_cache)
        rel_png = f"cap_frames_{lang}/ov_{idx:04d}.png"
        img = Image.new("RGBA", (res_x, res_y), (0, 0, 0, 0))
        if h_txt:
            draw_block(img, h_txt, lang, size=head_size, y_center=head_y, max_width=max_w,
                       fill=(255, 229, 0, 255), stroke=(0, 0, 0, 255), stroke_width=7)
        if c_txt:
            tokens = c_txt.split()
            pw_idx = _best_power_word_idx(tokens, lang)
            if lang in RTL or pw_idx < 0:
                draw_block(img, c_txt, lang, size=cap_size, y_center=cap_y, max_width=max_w,
                           fill=(255, 255, 255, 255), stroke=(0, 0, 0, 255), stroke_width=9)
            else:
                draw = ImageDraw.Draw(img)
                space_w = draw.textlength(" ", font=cap_fnt)
                word_widths = [draw.textlength(t, font=cap_fnt) for t in tokens]
                total_w = sum(word_widths) + space_w * max(len(tokens) - 1, 0)
                if total_w > max_w:
                    draw_block(img, c_txt, lang, size=cap_size, y_center=cap_y, max_width=max_w,
                               fill=(255, 255, 255, 255), stroke=(0, 0, 0, 255), stroke_width=9)
                else:
                    x = (res_x - total_w) / 2
                    y = cap_y - int(cap_size * 0.62)
                    for wi, (tok, ww) in enumerate(zip(tokens, word_widths)):
                        color = (255, 229, 0, 255) if wi == pw_idx else (255, 255, 255, 255)
                        draw.text((x, y), tok, font=cap_fnt, fill=color, stroke_width=9, stroke_fill=(0, 0, 0, 255))
                        x += ww + space_w
        img.save(run_dir / rel_png)
        state_cache[key] = rel_png
        return rel_png

    lines = ["ffconcat version 1.0"]
    last_png = render_state("", "")
    for t0, t1 in zip(filtered_pts[:-1], filtered_pts[1:]):
        dur = max(round(t1 - t0, 3), 0.02)
        tm = (t0 + t1) / 2.0
        h_active = next((h["text"] for h in headlines if h["start"] <= tm <= h["end"]), "")
        c_active = next((c["text"] for c in captions if c["start"] <= tm <= c["end"]), "")
        png_rel = render_state(h_active, c_active)
        lines.append(f"file '{png_rel}'")
        lines.append(f"duration {dur:.3f}")
        last_png = png_rel
    # ffconcat requires repeating the last file entry
    lines.append(f"file '{last_png}'")
    concat_rel = f"captions_track_{lang}.ffconcat"
    (run_dir / concat_rel).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return concat_rel


FOLLOW_LABELS = {"en": "SUBSCRIBE", "fr": "S'ABONNER", "ar": "اشترك"}


def write_follow_button(path: Path, lang: str, label: str | None = None) -> tuple[int, int]:
    """Render a transparent PNG 'subscribe/follow' pill (red, white label, bell) for the editor to overlay.
    Returns (width, height)."""
    from PIL import Image

    label = label or FOLLOW_LABELS.get(lang, FOLLOW_LABELS["en"])
    fnt = font(lang, 58)
    shown = visual(label, lang)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text_w = int(probe.textlength(shown, font=fnt))
    pad_x, bell_w, h = 56, 70, 128
    w = text_w + bell_w + pad_x * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(255, 0, 0, 255), outline=(255, 255, 255, 255), width=5)
    # bell glyph drawn with shapes (no emoji font needed), on the reading-start side of the label
    bx = w - pad_x - bell_w + 10 if lang in RTL else pad_x
    cx, cy = bx + 25, h // 2
    d.pieslice((cx - 22, cy - 28, cx + 22, cy + 16), 180, 360, fill="white")
    d.rectangle((cx - 22, cy - 6, cx + 22, cy + 16), fill="white")
    d.rectangle((cx - 28, cy + 14, cx + 28, cy + 21), fill="white")
    d.ellipse((cx - 7, cy + 22, cx + 7, cy + 34), fill="white")
    tx = pad_x if lang in RTL else pad_x + bell_w
    d.text((tx, (h - 58) // 2 - 8), shown, font=fnt, fill="white")
    img.save(path)
    return w, h


def write_ass(path: Path, lang: str, captions: list[dict], headlines: list[dict],
              size: tuple[int, int] = (1080, 1920)) -> None:
    """captions/headlines: [{start, end, text}] in seconds. Captions sit in the lower third,
    scene headlines (on-screen text) near the top. libass handles Arabic shaping and direction."""
    fam = ASS_FONTS.get(lang, ASS_FONTS["fr"])
    res_x, res_y = size
    is_landscape = res_x > res_y
    cap_size = 86 if is_landscape else 124
    head_size = 64 if is_landscape else 84
    cap_margin_v = 110 if is_landscape else 560
    head_margin_v = 65 if is_landscape else 230
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {res_x}
PlayResY: {res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{fam},{cap_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,9,3,2,70,70,{cap_margin_v},1
Style: Headline,{fam},{head_size},&H0000E5FF,&H0000E5FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,6,2,8,70,70,{head_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for h in headlines:
        events.append(f"Dialogue: 1,{_ass_time(h['start'])},{_ass_time(h['end'])},Headline,,0,0,0,,{{\\fad(150,150)}}{_ass_escape(h['text'])}")
    for c in captions:
        styled_txt = highlight_power_word(c["text"], lang)
        events.append(f"Dialogue: 0,{_ass_time(c['start'])},{_ass_time(c['end'])},Caption,,0,0,0,,{{\\fscx92\\fscy92\\t(0,90,\\fscx100\\fscy100)}}{styled_txt}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def caption_chunks(words: list[dict], max_words: int = 3, max_gap: float = 0.35) -> list[dict]:
    """Group word timings into short punchy caption chunks."""
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > max_gap or cur[-1]["text"][-1:] in ".?!،؟,"):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    out = []
    for i, c in enumerate(chunks):
        end = c[-1]["end"]
        nxt = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else end + 0.3
        out.append({"start": c[0]["start"], "end": min(max(end, c[0]["start"] + 0.4), nxt), "text": " ".join(w["text"] for w in c)})
    return out
