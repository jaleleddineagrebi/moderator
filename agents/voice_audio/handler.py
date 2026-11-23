import json
import random
import shutil

from moderator import ROOT
from moderator.engine.agent import Agent, StepContext
from moderator.tools import ffmpeg, history, tts
from moderator.tools.languages import normalize_langs

SCENE_GAP = 0.09  # crisp creator cut between scenes, seconds (eliminates dead air)
MAX_VOICEOVER = 55.0  # above this, re-record faster (the editor adds a short tail; Shorts must stay under 60s)
TARGET_VOICEOVER = 53.0
LONG_MAX_VOICEOVER = 400.0
LONG_TARGET_VOICEOVER = 340.0
MAX_SPEEDUP = 15  # percent; faster than this starts to sound rushed
# Chord progressions for the generated pad: (semitones from A3, "M"ajor or "m"inor) x 4 chords. Generated here, so there is
# no copyright to worry about. Each video gets a different progression, key, chord length and timbre (see music_variant).
PROGRESSIONS = [
    [(0, "m"), (-4, "M"), (3, "M"), (-2, "M")],   # Am F C G
    [(3, "M"), (-2, "M"), (0, "m"), (-4, "M")],   # C G Am F
    [(5, "m"), (1, "M"), (-4, "M"), (3, "M")],    # Dm Bb F C
    [(-5, "m"), (3, "M"), (-2, "M"), (5, "M")],   # Em C G D
    [(-2, "M"), (5, "M"), (7, "m"), (3, "M")],    # G D Em C
    [(-4, "M"), (3, "M"), (5, "m"), (1, "M")],    # F C Dm Bb
]


def music_variant(n: int, rng: random.Random) -> dict:
    """Pick this video's music: the progression walks through the list video after video, the rest is random."""
    return {
        "progression": PROGRESSIONS[n % len(PROGRESSIONS)],
        "transpose": rng.choice([-2, -1, 0, 1, 2]),
        "chord_seconds": rng.choice([4, 5, 6]),
        "overtone": rng.choice([0.2, 0.35, 0.5]),
        "lowpass": rng.choice([1500, 1800, 2200]),
        "echo": rng.choice(["0.8:0.7:120|240:0.25|0.15", "0.8:0.75:160|320:0.3|0.18", "0.8:0.6:90|180:0.2|0.1"]),
    }


def _chord_freqs(root_semitones: int, quality: str) -> tuple[float, float, float]:
    third = 3 if quality == "m" else 4
    return tuple(220.0 * 2 ** ((root_semitones + step) / 12) for step in (0, third, 7))


def pad_expression(variant: dict | None = None) -> str:
    v = variant or {"progression": PROGRESSIONS[0], "transpose": 0, "chord_seconds": 4, "overtone": 0.35}
    length, cycle = v["chord_seconds"], v["chord_seconds"] * 4
    chords = [_chord_freqs(root + v["transpose"], quality) for root, quality in v["progression"]]

    def note(i: int) -> str:
        f = [round(c[i], 2) for c in chords]
        return (f"if(lt(mod(t,{cycle}),{length}),{f[0]},if(lt(mod(t,{cycle}),{2 * length}),{f[1]},"
                f"if(lt(mod(t,{cycle}),{3 * length}),{f[2]},{f[3]})))")
    env = f"(0.55+0.45*sin(PI*mod(t,{length})/{length}))"  # swell inside each chord
    voices = "+".join(f"sin(2*PI*t*{note(i)})+{v['overtone']}*sin(4*PI*t*{note(i)})" for i in range(3))
    return f"0.09*{env}*({voices})"


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        script = ctx.read_json(ctx.upstream("script")["data"])
        langs = normalize_langs(ctx.params.get("languages"))
        voice_idx = {"primary_voice": 0, "alternate_voice": 1, "third_voice_slower": 2}.get(ctx.strategy, 0)
        is_long = str(ctx.params.get("format") or "short").lower() == "long"
        max_vo = LONG_MAX_VOICEOVER if is_long else MAX_VOICEOVER
        target_vo = LONG_TARGET_VOICEOVER if is_long else TARGET_VOICEOVER
        # Shorts are narrated a little fast; a 4-5 minute video needs a natural, unhurried pace
        base_rate = 0 if is_long else 6
        # videos made so far: walks the voice pool and the music progressions so consecutive videos sound different
        n = history.count()
        base_rate += (0, 2, -1, 3)[n % 4]  # tiny delivery variation on top of the voice change
        rate = f"{base_rate - 12:+d}%" if ctx.strategy == "third_voice_slower" else f"{base_rate:+d}%"
        if ctx.feedback:
            fb_low = ctx.feedback[-1]["comment"].lower()
            ctx.log(f"Revision feedback: {ctx.feedback[-1]['comment']}")
            # owner `/edit voice ...`: slower / faster / a different voice
            if any(w in fb_low for w in ("slower", "slow down", "calmer")):
                rate = f"{int(rate.rstrip('%')) - 8:+d}%"
            elif any(w in fb_low for w in ("faster", "speed up", "quicker")):
                rate = f"{int(rate.rstrip('%')) + 8:+d}%"
            if any(w in fb_low for w in ("different voice", "another voice", "other voice", "change voice",
                                         "new voice", "change the voice")):
                voice_idx = 1 if voice_idx == 0 else 0
            ctx.log(f"Voice settings for this revision: voice #{voice_idx + 1}, rate {rate}")
        ctx.set_inputs(script=ctx.upstream("script")["data"], languages=langs,
                       voices={l: tts.voice_for(l, voice_idx, n) for l in langs})
        outputs = {}
        max_total = 0.0
        for li, lang in enumerate(langs):
            voice = tts.voice_for(lang, voice_idx, n)
            ctx.log(f"Narrating {lang} with {voice}")
            vo, timings, total = await self._narrate(ctx, script, lang, voice, rate)
            if total > max_vo:
                # keep the video under limit whatever the script estimate was: re-record slightly faster
                speedup = min(MAX_SPEEDUP, int((total / target_vo - 1) * 100) + 1)
                faster = f"{int(rate.rstrip('%')) + speedup:+d}%"
                ctx.log(f"{lang} voiceover is {total:.1f}s; re-recording at rate {faster}", "warning")
                vo, timings, total = await self._narrate(ctx, script, lang, voice, faster)
            max_total = max(max_total, total)
            if len(langs) == 1:
                shutil.copy2(ctx.run_dir / vo, ctx.run_dir / "voiceover.mp3")
            outputs[f"voiceover_{lang}"] = vo
            outputs[f"timings_{lang}"] = ctx.write_json(f"timings_{lang}.json", {"voice": voice, "duration": total, "scenes": timings})
            ctx.log(f"{lang} voiceover: {total:.1f}s")
            ctx.progress(5 + 75 * (li + 1) / len(langs))

        outputs["music"], licenses = await self._music(ctx, max_dur=max_total, n=n)
        ctx.progress(90)
        outputs["whoosh"] = "sfx/whoosh.mp3"
        ctx.path("sfx/whoosh.mp3")
        await ffmpeg.run(["-f", "lavfi", "-i", "anoisesrc=d=0.5:c=pink:a=0.6", "-af",
                          "highpass=f=500,lowpass=f=4000,afade=t=in:d=0.22,afade=t=out:st=0.22:d=0.28,volume=0.5",
                          "-c:a", "libmp3lame", "-q:a", "4", "sfx/whoosh.mp3"], ctx.run_dir)
        outputs["licenses"] = ctx.write_json("audio/licenses.json", licenses)
        return outputs

    async def _narrate(self, ctx: StepContext, script: dict, lang: str, voice: str, rate: str) -> tuple[str, list, float]:
        """One mp3 per scene, joined with short pauses. Returns (voiceover path, scene timings, duration)."""
        parts, timings, t = [], [], 0.0
        for scene in script["scenes"]:
            part = ctx.path(f"audio/{lang}/{scene['id']}.mp3")
            words = await tts.synthesize(scene["vo"][lang], voice, part, rate=rate)
            dur = await ffmpeg.duration(part)
            if not words:
                ctx.log(f"{scene['id']} ({lang}): TTS emitted no WordBoundary events; estimating word timings", "warning")
                words = tts.fallback_word_timings(scene["vo"][lang], dur)
            timings.append({"scene": scene["id"], "start": round(t, 3), "end": round(t + dur, 3),
                            "words": [{**w, "start": round(w["start"] + t, 3), "end": round(w["end"] + t, 3)} for w in words]})
            parts.append(part.relative_to(ctx.run_dir).as_posix())
            t += dur + SCENE_GAP
        # concat scene parts with short silences, resampled to one clean 44.1k track
        inputs = []
        for rel in parts:
            inputs += ["-i", rel]
        gap = f"aevalsrc=0:d={SCENE_GAP}:s=44100"
        chains, labels = [], []
        for i in range(len(parts)):
            chains.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=mono[a{i}]")
            labels.append(f"[a{i}]")
            if i < len(parts) - 1:
                chains.append(f"{gap}[g{i}]")
                labels.append(f"[g{i}]")
        graph = ";".join(chains) + ";" + "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]"
        vo = f"voiceover_{lang}.mp3"
        await ffmpeg.run([*inputs, "-filter_complex", graph, "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2", vo], ctx.run_dir)
        return vo, timings, await ffmpeg.duration(ctx.run_dir / vo)

    async def _music(self, ctx: StepContext, max_dur: float = 55.0, n: int = 0) -> tuple[str, dict]:
        bed_sec = max(70, int(max_dur) + 15)
        fade_st = bed_sec - 4
        library = ROOT / "library" / "music"
        tracks = [p for p in library.glob("*.mp3") if (p.with_suffix(".json")).exists()]
        if tracks:
            track = random.choice(tracks)
            meta = json.loads(track.with_suffix(".json").read_text(encoding="utf-8"))
            ctx.log(f"Music from library: {track.name} ({meta.get('license')})")
            await ffmpeg.run(["-i", str(track), "-t", str(bed_sec), "-af", f"afade=t=out:st={fade_st}:d=4", "-c:a", "libmp3lame", "-q:a", "4", "music.mp3"], ctx.run_dir)
            licenses = {"music": {"source": track.name, **meta}}
        else:
            variant = music_variant(n, random.Random(ctx.store.data.get("run_id", "")))
            ctx.log(f"Generating an ambient music bed (no library tracks): progression #{n % len(PROGRESSIONS) + 1}, "
                    f"transpose {variant['transpose']:+d}, {variant['chord_seconds']}s chords")
            await ffmpeg.run(["-f", "lavfi", "-i", f"aevalsrc='{pad_expression(variant)}':s=44100:d={bed_sec}", "-af",
                              f"lowpass=f={variant['lowpass']},aecho={variant['echo']},afade=t=in:d=2,afade=t=out:st={fade_st}:d=4,volume=0.8",
                              "-c:a", "libmp3lame", "-q:a", "4", "music.mp3"], ctx.run_dir)
            licenses = {"music": {"source": "generated by voice_audio agent (ffmpeg synthesis)", "license": "original work, no third-party rights"}}
        licenses["sfx"] = {"source": "generated by voice_audio agent (ffmpeg noise synthesis)", "license": "original work, no third-party rights"}
        licenses["voice"] = {"source": "Microsoft Edge neural TTS via edge-tts", "license": "synthetic voice; no third-party performance rights"}
        return "music.mp3", licenses
