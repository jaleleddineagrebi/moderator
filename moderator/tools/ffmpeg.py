"""ffmpeg/ffprobe helpers. Commands run with cwd set to the run folder so filter paths stay relative
(Windows drive letters need awkward escaping inside ffmpeg filter strings)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from functools import cache
from pathlib import Path

W, H, FPS = 1080, 1920, 30


class FFmpegError(Exception):
    pass


@cache
def binary(name: str = "ffmpeg") -> str:
    found = shutil.which(name)
    if found:
        return found
    for extra in (Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
        cand = extra / name
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    # winget installs ffmpeg here; PATH only picks it up in new shells
    packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if packages.exists():
        for exe in sorted(packages.glob(f"Gyan.FFmpeg*/*/bin/{name}.exe"), reverse=True):
            return str(exe)
    hint = ("brew install ffmpeg" if sys.platform == "darwin"
            else "winget install Gyan.FFmpeg" if sys.platform == "win32"
            else "sudo apt-get install ffmpeg")
    raise FFmpegError(f"{name} not found. Install it with: {hint}")


async def run(args: list[str], cwd: Path, timeout: int = 900) -> str:
    cmd = [binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = await asyncio.to_thread(subprocess.run, cmd, cwd=cwd, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=timeout)
    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg failed: {proc.stderr.strip()[-1500:]}")
    return proc.stderr


async def probe(path: Path) -> dict:
    cmd = [binary("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    proc = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed on {path.name}: {proc.stderr.strip()[-500:]}")
    return json.loads(proc.stdout)


async def duration(path: Path) -> float:
    return float((await probe(path))["format"]["duration"])


async def loudness(path: Path, cwd: Path) -> dict:
    """Integrated loudness (LUFS) and true peak (dBTP) via the ebur128 filter."""
    cmd = [binary("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path), "-filter_complex", "ebur128=peak=true", "-f", "null", "-"]
    proc = await asyncio.to_thread(subprocess.run, cmd, cwd=cwd, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=600)
    summary = proc.stderr[proc.stderr.rfind("Summary:"):]
    integrated = re.search(r"I:\s+(-?[\d.]+) LUFS", summary)
    peak = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    if not integrated:
        raise FFmpegError("could not measure loudness")
    return {"lufs": float(integrated.group(1)), "true_peak_db": float(peak.group(1)) if peak and peak.group(1) != "-inf" else None}


COVER_VF = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},eq=contrast=1.06:saturation=1.14,setsar=1,fps={FPS}"


async def normalize_clip(src: Path, dst: Path, cwd: Path, max_seconds: float = 12,
                         size: tuple[int, int] = (W, H)) -> None:
    """Any video -> silent normalized 30fps H.264 clip (1080x1920 for Shorts, 1920x1080 for Long-form)."""
    w, h = size
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},eq=contrast=1.06:saturation=1.14,setsar=1,fps={FPS}"
    await run(["-i", str(src), "-t", f"{max_seconds}", "-vf", vf, "-an", "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(dst)], cwd)


async def still_to_clip(src: Path, dst: Path, cwd: Path, seconds: float = 8, zoom_in: bool = True,
                        size: tuple[int, int] = (W, H)) -> None:
    """Still image -> slow Ken Burns zoom clip (1080x1920 for Shorts, 1920x1080 for Long-form)."""
    w, h = size
    frames = int(seconds * FPS)
    z = "min(zoom+0.0009,1.15)" if zoom_in else "if(eq(on,0),1.15,max(zoom-0.0009,1.0))"
    vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
          f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={FPS},setsar=1")
    await run(["-loop", "1", "-i", str(src), "-vf", vf, "-t", f"{seconds}", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "20", "-pix_fmt", "yuv420p", str(dst)], cwd)


async def frame_at(src: Path, dst: Path, cwd: Path, at: float = 1.0) -> None:
    await run(["-ss", f"{at}", "-i", str(src), "-frames:v", "1", str(dst)], cwd)
