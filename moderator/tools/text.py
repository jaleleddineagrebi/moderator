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


FOLLOW_LABELS = {"en": "FOLLOW", "fr": "S'ABONNER", "ar": "اشترك"}


def write_follow_button(path: Path, lang: str, label: str | None = None) -> tuple[int, int]:
    """Render a transparent PNG 'follow' pill (red, white label, bell) for the editor to overlay.
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


def write_ass(path: Path, lang: str, captions: list[dict], headlines: list[dict]) -> None:
    """captions/headlines: [{start, end, text}] in seconds. Captions sit in the lower third,
    scene headlines (on-screen text) near the top. libass handles Arabic shaping and direction."""
    fam = ASS_FONTS.get(lang, ASS_FONTS["fr"])
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{fam},124,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,9,3,2,70,70,560,1
Style: Headline,{fam},84,&H0000E5FF,&H0000E5FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,6,2,8,70,70,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for h in headlines:
        events.append(f"Dialogue: 1,{_ass_time(h['start'])},{_ass_time(h['end'])},Headline,,0,0,0,,{{\\fad(150,150)}}{_ass_escape(h['text'])}")
    for c in captions:
        events.append(f"Dialogue: 0,{_ass_time(c['start'])},{_ass_time(c['end'])},Caption,,0,0,0,,{{\\fscx92\\fscy92\\t(0,90,\\fscx100\\fscy100)}}{_ass_escape(c['text'])}")
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
