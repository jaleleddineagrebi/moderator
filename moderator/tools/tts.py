"""Free neural text-to-speech through edge-tts, with per-word timings for captions."""

from __future__ import annotations

from pathlib import Path

import edge_tts

from .languages import LANGS


def voice_for(lang: str, index: int) -> str:
    """index 0 is the normal voice; higher indexes are retry fallbacks (clamped to what exists)."""
    voices = LANGS[lang]["voices"]
    return voices[min(index, len(voices) - 1)]


async def synthesize(text: str, voice: str, out: Path, rate: str = "+0%") -> list[dict]:
    """Write an mp3 and return word timings [{start, end, text}] in seconds."""
    words = []
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with out.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append({"start": round(start, 3), "end": round(start + chunk["duration"] / 1e7, 3), "text": chunk["text"]})
    if out.stat().st_size == 0:
        raise RuntimeError(f"edge-tts returned no audio for voice {voice}")
    return words
