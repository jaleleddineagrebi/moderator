import json
import random

from moderator import ROOT
from moderator.engine.agent import Agent, StepContext
from moderator.tools import ffmpeg, tts

SCENE_GAP = 0.18  # breath between scenes, seconds
# A-minor / F / C / G pad, 4 seconds per chord. Generated here, so there is no copyright to worry about.
CHORDS = [(220.00, 261.63, 329.63), (174.61, 220.00, 261.63), (261.63, 329.63, 392.00), (196.00, 246.94, 293.66)]


def pad_expression() -> str:
    def note(i: int) -> str:
        f = [c[i] for c in CHORDS]
        return f"if(lt(mod(t,16),4),{f[0]},if(lt(mod(t,16),8),{f[1]},if(lt(mod(t,16),12),{f[2]},{f[3]})))"
    env = "(0.55+0.45*sin(PI*mod(t,4)/4))"  # swell inside each chord
    voices = "+".join(f"sin(2*PI*t*{note(i)})+0.35*sin(4*PI*t*{note(i)})" for i in range(3))
    return f"0.09*{env}*({voices})"


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        script = ctx.read_json(ctx.upstream("script")["data"])
        langs = ctx.params.get("languages", ["ar", "fr"])
        voice_idx = {"primary_voice": 0, "alternate_voice": 1, "third_voice_slower": 2}.get(ctx.strategy, 0)
        rate = "-6%" if ctx.strategy == "third_voice_slower" else "+0%"
        ctx.set_inputs(script=ctx.upstream("script")["data"], languages=langs,
                       voices={l: tts.voice_for(l, voice_idx) for l in langs})
        if ctx.feedback:
            ctx.log(f"Revision feedback: {ctx.feedback[-1]['comment']}")
        outputs = {}
        n_total = len(langs) * len(script["scenes"])
        done = 0
        for lang in langs:
            voice = tts.voice_for(lang, voice_idx)
            ctx.log(f"Narrating {lang} with {voice}")
            parts, timings, t = [], [], 0.0
            for scene in script["scenes"]:
                part = ctx.path(f"audio/{lang}/{scene['id']}.mp3")
                words = await tts.synthesize(scene["vo"][lang], voice, part, rate=rate)
                dur = await ffmpeg.duration(part)
                timings.append({"scene": scene["id"], "start": round(t, 3), "end": round(t + dur, 3),
                                "words": [{**w, "start": round(w["start"] + t, 3), "end": round(w["end"] + t, 3)} for w in words]})
                parts.append(part.relative_to(ctx.run_dir).as_posix())
                t += dur + SCENE_GAP
                done += 1
                ctx.progress(5 + 70 * done / n_total)
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
            total = await ffmpeg.duration(ctx.run_dir / vo)
            outputs[f"voiceover_{lang}"] = vo
            outputs[f"timings_{lang}"] = ctx.write_json(f"timings_{lang}.json", {"voice": voice, "duration": total, "scenes": timings})
            ctx.log(f"{lang} voiceover: {total:.1f}s")

        outputs["music"], licenses = await self._music(ctx)
        ctx.progress(90)
        outputs["whoosh"] = "sfx/whoosh.mp3"
        ctx.path("sfx/whoosh.mp3")
        await ffmpeg.run(["-f", "lavfi", "-i", "anoisesrc=d=0.5:c=pink:a=0.6", "-af",
                          "highpass=f=500,lowpass=f=4000,afade=t=in:d=0.22,afade=t=out:st=0.22:d=0.28,volume=0.5",
                          "-c:a", "libmp3lame", "-q:a", "4", "sfx/whoosh.mp3"], ctx.run_dir)
        outputs["licenses"] = ctx.write_json("audio/licenses.json", licenses)
        return outputs

    async def _music(self, ctx: StepContext) -> tuple[str, dict]:
        library = ROOT / "library" / "music"
        tracks = [p for p in library.glob("*.mp3") if (p.with_suffix(".json")).exists()]
        if tracks:
            track = random.choice(tracks)
            meta = json.loads(track.with_suffix(".json").read_text(encoding="utf-8"))
            ctx.log(f"Music from library: {track.name} ({meta.get('license')})")
            await ffmpeg.run(["-i", str(track), "-t", "70", "-af", "afade=t=out:st=66:d=4", "-c:a", "libmp3lame", "-q:a", "4", "music.mp3"], ctx.run_dir)
            licenses = {"music": {"source": track.name, **meta}}
        else:
            ctx.log("Generating an ambient music bed (no library tracks with license files found)")
            await ffmpeg.run(["-f", "lavfi", "-i", f"aevalsrc='{pad_expression()}':s=44100:d=70", "-af",
                              "lowpass=f=1800,aecho=0.8:0.7:120|240:0.25|0.15,afade=t=in:d=2,afade=t=out:st=66:d=4,volume=0.8",
                              "-c:a", "libmp3lame", "-q:a", "4", "music.mp3"], ctx.run_dir)
            licenses = {"music": {"source": "generated by voice_audio agent (ffmpeg synthesis)", "license": "original work, no third-party rights"}}
        licenses["sfx"] = {"source": "generated by voice_audio agent (ffmpeg noise synthesis)", "license": "original work, no third-party rights"}
        licenses["voice"] = {"source": "Microsoft Edge neural TTS via edge-tts", "license": "synthetic voice; no third-party performance rights"}
        return "music.mp3", licenses
