"""Helpers for long (16:9) videos: real chapter timestamps for the YouTube description and an SRT caption file.

Both are built from the real scene timings of the voiceover, so nothing is guessed by a language model."""

from __future__ import annotations

MIN_CHAPTER_SECONDS = 10.0  # YouTube ignores chapters shorter than 10 s
MIN_CHAPTERS = 3  # ...and needs at least 3, the first one at 0:00


def fmt_clock(seconds: float) -> str:
    """m:ss (or h:mm:ss) as YouTube chapter lines expect it."""
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def chapter_lines(scenes: list[dict], timing_scenes: list[dict], lang: str = "en") -> list[str]:
    """['0:00 Intro', '0:42 Why it happens', ...] from the script's `chapter` titles and the voiceover scene starts.

    Returns [] when YouTube would not accept them (fewer than 3 chapters or any shorter than 10 s)."""
    start_of = {t["scene"]: float(t["start"]) for t in timing_scenes}
    marks: list[tuple[float, str]] = []
    for sc in scenes:
        title = str(sc.get("chapter") or "").strip()
        if title and sc["id"] in start_of:
            marks.append((start_of[sc["id"]], title[:60]))
    if not marks:
        return []
    marks[0] = (0.0, marks[0][1])  # the first chapter must start at 0:00
    marks = sorted(marks)
    if len(marks) < MIN_CHAPTERS:
        return []
    end = float(timing_scenes[-1]["end"]) if timing_scenes else 0.0
    bounds = [m[0] for m in marks] + [end]
    if any(b - a < MIN_CHAPTER_SECONDS for a, b in zip(bounds, bounds[1:])):
        return []
    return [f"{fmt_clock(t)} {title}" for t, title in marks]


def srt_time(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(timing_scenes: list[dict], max_words: int = 9, max_seconds: float = 4.5) -> str:
    """SRT captions from per-word timings: a new cue every `max_words` words or `max_seconds`."""
    cues: list[tuple[float, float, str]] = []
    for sc in timing_scenes:
        words = sc.get("words") or []
        i = 0
        while i < len(words):
            group = [words[i]]
            i += 1
            while i < len(words) and len(group) < max_words and words[i]["end"] - group[0]["start"] <= max_seconds:
                group.append(words[i])
                i += 1
            cues.append((group[0]["start"], group[-1]["end"], " ".join(w["text"] for w in group)))
    blocks = []
    for n, (a, b, text) in enumerate(cues, 1):
        b = max(b, a + 0.3)
        blocks.append(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n")
    return "\n".join(blocks)
