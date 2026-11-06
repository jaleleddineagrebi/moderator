import os
import shutil

from moderator.engine.agent import Agent, StepContext
from moderator.tools import ffmpeg, text
from moderator.tools.languages import normalize_langs

XFADE = 0.25
TRANSITIONS = ["slideleft", "smoothup", "fade", "slideright", "circleopen", "smoothleft"]
TAIL = 0.7  # seconds of picture and music after the last word


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        script = ctx.read_json(ctx.upstream("script")["data"])
        visuals = ctx.upstream("visuals")["scenes"]
        audio = ctx.upstream("audio")
        langs = normalize_langs(ctx.params.get("languages"))
        music_vol = float(ctx.options.get("music_volume", 0.13))
        transitions = ctx.strategy == "transitions"
        sfx = ctx.strategy != "hard_cuts_no_sfx"
        ctx.set_inputs(scenes=visuals, audio={k: v for k, v in audio.items() if k != "licenses"},
                       languages=langs, strategy=ctx.strategy)
        if ctx.feedback:
            fb_low = ctx.feedback[-1]["comment"].lower()
            ctx.log(f"Revision feedback: {ctx.feedback[-1]['comment']}")
            if "music" in fb_low and any(w in fb_low for w in ("loud", "lower", "quiet", "softer")):
                music_vol *= 0.6
                ctx.log("Lowering music level")
            elif "music" in fb_low and any(w in fb_low for w in ("louder", "higher", "boost")):
                music_vol = min(0.35, music_vol * 1.4)
                ctx.log("Raising music level")
            if "hard cut" in fb_low or "no transition" in fb_low:
                transitions = False
            if "no sfx" in fb_low or "remove sfx" in fb_low or "no whoosh" in fb_low:
                sfx = False
        follow_button = bool(ctx.options.get("follow_button", True))
        follow_start = float(ctx.options.get("follow_button_start", 3.0))
        follow_y = int(ctx.options.get("follow_button_y", 1440))
        follow_label = ctx.options.get("follow_button_label") or {}  # optional per-language override
        fonts_dir = text.escape_filter_arg(os.path.relpath(text.FONTS_DIR, ctx.run_dir))

        outputs = {}
        for li, lang in enumerate(langs):
            timing = ctx.read_json(audio[f"timings_{lang}"])
            scenes = timing["scenes"]
            # each scene lasts until the next one starts; the last one keeps a short tail
            durs = [scenes[i + 1]["start"] - s["start"] for i, s in enumerate(scenes[:-1])]
            durs.append(timing["duration"] - scenes[-1]["start"] + TAIL)
            total = sum(durs)

            captions, headlines = [], []
            for s, sc, d in zip(script["scenes"], scenes, durs):
                captions += text.caption_chunks(sc["words"], max_words=3)
                headlines.append({"start": sc["start"] + 0.05, "end": sc["start"] + d - 0.05, "text": s["on_screen"][lang]})
            ass = f"captions_{lang}.ass"
            text.write_ass(ctx.run_dir / ass, lang, captions, headlines)
            ass_escaped = text.escape_filter_arg(ass)

            args, chains = [], []
            for i, (clip, d) in enumerate(zip(visuals, durs)):
                length = d + (XFADE if transitions and i < len(durs) - 1 else 0)
                args += ["-stream_loop", "-1", "-t", f"{length:.3f}", "-i", clip]
                chains.append(f"[{i}:v]trim=duration={length:.3f},setpts=PTS-STARTPTS,fps={ffmpeg.FPS},format=yuv420p,setsar=1[v{i}]")
            n = len(visuals)
            cut_times, acc = [], 0.0
            for d in durs[:-1]:
                acc += d
                cut_times.append(acc)
            if transitions and n > 1:
                prev = "v0"
                for k, offset in enumerate(cut_times, start=1):
                    chains.append(f"[{prev}][v{k}]xfade=transition={TRANSITIONS[(k - 1) % len(TRANSITIONS)]}:duration={XFADE}:offset={offset:.3f}[x{k}]")
                    prev = f"x{k}"
            elif n > 1:
                chains.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[x]")
                prev = "x"
            else:
                prev = "v0"
            vo_i, mu_i, wh_i = n, n + 1, n + 2
            args += ["-i", audio[f"voiceover_{lang}"], "-stream_loop", "-1", "-i", audio["music"], "-i", audio["whoosh"]]
            if follow_button:
                # follow button pill pops in after the hook and stays to the end, between captions and the YouTube UI
                png = f"follow_button_{lang}.png"
                text.write_follow_button(ctx.run_dir / png, lang, follow_label.get(lang))
                btn_i = n + 3
                args += ["-loop", "1", "-i", png]
                chains.append(f"[{prev}]subtitles='{ass_escaped}':fontsdir='{fonts_dir}'[sub]")
                chains.append(f"[{btn_i}:v]format=rgba,fade=t=in:st={follow_start:.2f}:d=0.4:alpha=1[btn]")
                chains.append(f"[sub][btn]overlay=x=(W-w)/2:y={follow_y}:shortest=1:eof_action=pass,format=yuv420p[vout]")
            else:
                chains.append(f"[{prev}]subtitles='{ass_escaped}':fontsdir='{fonts_dir}'[vout]")
            chains.append(f"[{vo_i}:a]aresample=44100,aformat=channel_layouts=stereo,apad=whole_dur={total:.3f}[vo]")
            chains.append("[vo]asplit=2[vo1][vokey]")
            chains.append(f"[{mu_i}:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:{total:.3f},volume={music_vol},"
                          f"afade=t=out:st={max(total - 1.2, 0):.3f}:d=1.2[mus]")
            chains.append("[mus][vokey]sidechaincompress=threshold=0.04:ratio=6:attack=15:release=350[duck]")
            mix = ["[vo1]", "[duck]"]
            if sfx and cut_times:
                chains.append(f"[{wh_i}:a]aresample=44100,aformat=channel_layouts=stereo,asplit={len(cut_times)}"
                              + "".join(f"[w{k}]" for k in range(len(cut_times))))
                for k, t in enumerate(cut_times):
                    ms = max(int((t - 0.15) * 1000), 0)
                    chains.append(f"[w{k}]adelay={ms}|{ms},volume=0.35[wd{k}]")
                    mix.append(f"[wd{k}]")
            chains.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first,"
                          "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100[aout]")

            out = f"final_short_{lang}.mp4"
            ctx.log(f"Rendering {lang}: {n} scenes, {total:.1f}s, {'xfade transitions' if transitions else 'hard cuts'}")
            await ffmpeg.run([*args, "-filter_complex", ";".join(chains), "-map", "[vout]", "-map", "[aout]",
                              "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                              "-r", str(ffmpeg.FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out],
                             ctx.run_dir, timeout=1800)
            if len(langs) == 1:
                shutil.copy2(ctx.run_dir / out, ctx.run_dir / "final_short.mp4")
            outputs[f"video_{lang}"] = out
            outputs[f"captions_{lang}"] = ass
            ctx.progress(100 * (li + 1) / len(langs))
        return outputs
