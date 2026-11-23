"""Consecutive videos must not all sound the same: voice rotation and music variety."""

import random
import shutil
import subprocess

import pytest

from agents.voice_audio.handler import PROGRESSIONS, music_variant, pad_expression
from moderator.tools import history, tts
from moderator.tools.languages import LANGS


def test_voices_rotate_with_the_number_of_videos_made():
    pool = LANGS["en"]["voices"]
    assert len(pool) >= 5
    first = [tts.voice_for("en", 0, n) for n in range(len(pool))]
    assert sorted(first) == sorted(pool)  # every voice gets its turn
    assert all(tts.voice_for("en", 0, n) != tts.voice_for("en", 0, n + 1) for n in range(20))  # never twice in a row
    # a retry / owner "/edit voice" moves to a different voice than the one first used
    assert tts.voice_for("en", 1, 3) != tts.voice_for("en", 0, 3)
    # languages with a small pool still work
    assert tts.voice_for("ar", 5, 7) in LANGS["ar"]["voices"]
    # without a rotation the behaviour is unchanged: the first voice
    assert tts.voice_for("en", 0) == pool[0]


def test_history_count_is_not_capped_like_recent(tmp_path):
    path = tmp_path / "topics.jsonl"
    for i in range(75):
        history.record(f"run_{i}", f"Topic {i}", path=path)
    assert len(history.recent(path=path)) == 60  # recent() is capped...
    assert history.count(path) == 75  # ...so rotations must use count()
    history.record("run_74", "Topic 74 revised", path=path)  # a revision of the same run does not add a video
    assert history.count(path) == 75


def test_music_differs_between_videos():
    variants = [music_variant(n, random.Random(f"run_{n}")) for n in range(len(PROGRESSIONS))]
    assert len({str(v["progression"]) for v in variants}) == len(PROGRESSIONS)  # a different progression each time
    expressions = {pad_expression(v) for v in variants}
    assert len(expressions) == len(PROGRESSIONS)
    assert pad_expression() == pad_expression(None)  # the old default stays available


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_every_generated_music_expression_is_valid_for_ffmpeg(tmp_path):
    for n in range(len(PROGRESSIONS)):
        v = music_variant(n, random.Random(n))
        out = tmp_path / f"m{n}.mp3"
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"aevalsrc='{pad_expression(v)}':s=44100:d=1", "-af",
                        f"lowpass=f={v['lowpass']},aecho={v['echo']}", str(out)], check=True, capture_output=True)
        assert out.stat().st_size > 0
