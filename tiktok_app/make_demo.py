"""Build tiktok_app/demo_video.mp4 from title slides + a real generated short.

Run: .venv/bin/python tiktok_app/make_demo.py
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "build"
OUT.mkdir(exist_ok=True)
FONT = ROOT.parent / "library" / "fonts" / "NotoSans-Bold.ttf"
W, H = 1280, 720
FFMPEG = "/opt/homebrew/bin/ffmpeg"
RUN = ROOT.parent / "runs" / "20261103_test_youtube_short"
SHORT = OUT / "preview.mp4"  # assembled below from the run's scene clips + voiceover

SLIDES = [
    ("Moderator Shorts", ["Lifestyle short videos, published to your own TikTok account", "Demo for TikTok app review"], 5),
    ("Step 1: Idea and script", ["The app researches a lifestyle topic", "and writes a short script with a hook"], 5),
    ("Step 2: Video is generated", ["Stock footage, voiceover and captions", "are assembled into a vertical short"], 4),
    ("PREVIEW", None, 12),
    ("Step 3: Owner approval", ["The owner reviews the video, title and hashtags", "Nothing is posted without explicit approval"], 6),
    ("Step 4: Login Kit", ["The owner logs in with TikTok and grants consent", "Scopes: user.info.basic, video.publish, video.upload"], 6),
    ("Step 5: Content Posting API", ["The approved video is uploaded to the", "owner's own TikTok account"], 6),
    ("Privacy", ["Only the owner's account is connected", "No data from other users is collected", "Tokens are encrypted and revocable at any time"], 6),
]


def font(size):
    return ImageFont.truetype(str(FONT), size)


def slide(i, title, lines):
    img = Image.new("RGB", (W, H), (14, 18, 32))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill=(0, 200, 190))
    d.text((80, 200), title, font=font(64), fill=(255, 255, 255))
    y = 320
    for ln in lines:
        d.text((80, y), ln, font=font(36), fill=(190, 200, 220))
        y += 60
    p = OUT / f"s{i}.png"
    img.save(p)
    return p


def run(*a):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *a], check=True)


scenes = sorted((RUN / "assets").glob("scene_0*.mp4"))
slist = OUT / "scenes.txt"
slist.write_text("".join(f"file '{p}'\n" for p in scenes))
run("-f", "concat", "-safe", "0", "-i", str(slist), "-i", str(RUN / "voiceover_en.mp3"),
    "-map", "0:v", "-map", "1:a", "-vf", "scale=1080:1920,fps=30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-shortest", str(SHORT))

parts = []
for i, (title, lines, dur) in enumerate(SLIDES):
    seg = OUT / f"seg{i}.mp4"
    if lines is None:
        run("-i", str(SHORT), "-t", str(dur),
            "-vf", f"scale=-2:{H},pad={W}:{H}:(ow-iw)/2:0:color=0x0e1220,fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2", str(seg))
    else:
        png = slide(i, title, lines)
        run("-loop", "1", "-t", str(dur), "-i", str(png),
            "-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", "fps=30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(seg))
    parts.append(seg)

lst = OUT / "list.txt"
lst.write_text("".join(f"file '{p}'\n" for p in parts))
run("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(ROOT / "demo_video.mp4"))
print("wrote", ROOT / "demo_video.mp4")
