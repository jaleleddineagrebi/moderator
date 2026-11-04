import json

from moderator.engine.agent import Agent, StepContext
from moderator.tools import ffmpeg
from moderator.tools.languages import describe, names, normalize_langs, sensitivity_guidance


def make_review_schema(langs: list[str]) -> dict:
    lang_enum = [*langs, "all"] if len(langs) > 1 else list(langs)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["issues"],
        "properties": {"issues": {"type": "array", "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["severity", "area", "language", "detail", "send_to"],
            "properties": {
                "severity": {"type": "string", "enum": ["blocker", "minor"]},
                "area": {"type": "string", "enum": ["spelling", "grammar", "accuracy", "copyright", "sensitivity", "metadata", "visual_fit"]},
                "language": {"type": "string", "enum": lang_enum},
                "detail": {"type": "string", "description": "what is wrong and the exact fix"},
                "send_to": {"type": "string", "enum": ["script", "packaging", "visuals", "edit"]},
            },
        }}},
    }


class Handler(Agent):
    async def run(self, ctx: StepContext) -> dict[str, str]:
        langs = normalize_langs(ctx.params.get("languages"))
        edit = ctx.upstream("edit")
        script = ctx.read_json(ctx.upstream("script")["data"])
        meta = ctx.read_json(ctx.upstream("packaging")["metadata"])
        audio = ctx.upstream("audio")
        ctx.set_inputs(videos={l: edit[f"video_{l}"] for l in langs}, languages=langs,
                       metadata=ctx.upstream("packaging")["metadata"])

        checks: list[dict] = []

        def check(name, ok, detail, send_to=None, lang=None, severity="blocker"):
            checks.append({"check": name, "lang": lang, "ok": bool(ok), "detail": detail,
                           "send_to": None if ok else send_to, "severity": severity})

        for li, lang in enumerate(langs):
            video = ctx.run_dir / edit[f"video_{lang}"]
            info = await ffmpeg.probe(video)
            v = next(s for s in info["streams"] if s["codec_type"] == "video")
            a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
            dur = float(info["format"]["duration"])
            check("length", 15 <= dur < 60, f"{dur:.1f}s (must be under 60s; target 32-50s)", "script", lang)
            check("target length", 28 <= dur <= 58, f"{dur:.1f}s", "script", lang, "minor")
            check("aspect ratio", (v["width"], v["height"]) == (1080, 1920), f"{v['width']}x{v['height']}", "edit", lang)
            check("video codec", v["codec_name"] == "h264", v["codec_name"], "edit", lang)
            check("audio track", a is not None, "present" if a else "missing", "edit", lang)

            lv = await ffmpeg.loudness(video, ctx.run_dir)
            ok_lufs = -16.5 <= lv["lufs"] <= -11.5
            ok_peak = lv["true_peak_db"] is None or lv["true_peak_db"] <= -0.5
            check("loudness", ok_lufs and ok_peak, f"{lv['lufs']:.1f} LUFS, peak {lv['true_peak_db']} dBFS (target -14 LUFS, peak <= -1)", "edit", lang)

            # hook timing: scene 1 should land quickly (target <= 3.5s, hard blocker > 5.0s)
            timing = ctx.read_json(audio[f"timings_{lang}"])
            if timing["scenes"]:
                hook_dur = timing["scenes"][0]["end"] - timing["scenes"][0]["start"]
                check("hook timing", hook_dur <= 5.0,
                      f"scene_01 spoken in {hook_dur:.1f}s (target <= 3s)", "script", lang,
                      "blocker" if hook_dur > 5.0 else "minor")
                if 3.5 < hook_dur <= 5.0:
                    check("hook sharpness", False, f"scene_01 is {hook_dur:.1f}s (tighter <3.5s performs better)", "script", lang, "minor")

            # caption sync: every spoken word must be covered by a caption that is on screen when it is said
            words = [w for s in timing["scenes"] for w in s["words"]]
            events = parse_ass(ctx.run_dir / edit[f"captions_{lang}"])
            uncovered = [w["text"] for w in words if not any(e[0] - 0.05 <= w["start"] <= e[1] + 0.05 for e in events)]
            late = [e for e in events if e[1] > dur + 0.1]
            check("caption sync", bool(words) and not uncovered and not late,
                  f"{len(words)} words, {len(events)} caption events"
                  + ("; no word timings!" if not words else "")
                  + (f"; uncovered: {uncovered[:5]}" if uncovered else "")
                  + (f"; {len(late)} captions after the end" if late else ""), "edit", lang)
            ctx.progress(10 + 50 * (li + 1) / len(langs))

        licenses = ctx.read_json(ctx.upstream("visuals")["licenses"])
        bad = [l["scene"] for l in licenses if not l.get("license")]
        missing = [s["id"] for s in script["scenes"] if s["id"] not in {l["scene"] for l in licenses}]
        check("visual licenses", not bad and not missing,
              f"{len(licenses)} assets: " + ", ".join(sorted({l['provider'] for l in licenses}))
              + (f"; unlicensed {bad}" if bad else "") + (f"; missing {missing}" if missing else ""), "visuals")
        audio_lic = ctx.read_json(audio["licenses"])
        check("audio licenses", all(v.get("license") for v in audio_lic.values()),
              "; ".join(f"{k}: {v.get('license')}" for k, v in audio_lic.items()), "audio")

        if ctx.strategy != "technical_only":
            payload = {"script": [{"id": s["id"], "vo": s["vo"], "on_screen": s["on_screen"]} for s in script["scenes"]],
                       "metadata": meta, "visual_sources": [{k: l.get(k) for k in ("scene", "provider", "query")} for l in licenses]}
            review = await ctx.llm.ask(f"""You are the final QA reviewer for a YouTube Short published in {names(langs)}.
Intended writing style per language (do NOT flag dialect words or spellings that match it as errors):
{describe(langs)}
Check the narration, on-screen text, visual queries and metadata for:
- spelling and grammar mistakes in each language
- factual errors
- copyright or trademark problems (brands, celebrities, copyrighted characters, song names)
- content sensitivity: {sensitivity_guidance(langs)}
Only report real problems with an exact fix. Use severity "blocker" only for errors a viewer would notice or that create risk.
send_to: "script" for narration/on-screen text, "packaging" for title/description/hashtags/thumbnail text, "visuals" for problematic stock queries/clips, "edit" for caption/pacing problems.

{json.dumps(payload, ensure_ascii=False, indent=1)}""", schema=make_review_schema(langs))
            for issue in review["issues"]:
                check(f"{issue['area']} review", False, issue["detail"], issue["send_to"],
                      issue["language"], issue["severity"])
        ctx.progress(90)

        blockers = [c for c in checks if not c["ok"] and c["severity"] == "blocker"]
        passed = not blockers
        report = {"passed": passed, "revision_round": ctx.revision_round, "checks": checks}
        out = ctx.write_json("qa_report.json", report)
        md = [f"# QA report: {'PASSED' if passed else 'CHANGES NEEDED'}", ""]
        for c in checks:
            icon = "✅" if c["ok"] else ("❌" if c["severity"] == "blocker" else "⚠️")
            lang = f" [{c['lang']}]" if c["lang"] else ""
            sent = f" → sent to {c['send_to']}" if c["send_to"] and c["severity"] == "blocker" else ""
            md.append(f"- {icon} **{c['check']}**{lang}: {c['detail']}{sent}")
        ctx.path("qa_report.md").write_text("\n".join(md), encoding="utf-8")

        grouped: dict[str, list[str]] = {}
        for c in blockers:
            grouped.setdefault(c["send_to"], []).append(f"[{c['lang'] or 'all'}] {c['check']}: {c['detail']}")
        for target, items in grouped.items():
            ctx.request_revision(target, "QA found:\n" + "\n".join(items))
        ctx.log("All checks passed" if passed else f"{len(blockers)} blocking issue(s); sending back to: {', '.join(grouped)}",
                "info" if passed else "warning")
        outputs = {"report": "qa_report.md", "data": out}
        outputs.update({f"video_{l}": edit[f"video_{l}"] for l in langs})
        outputs.update({f"thumbnail_{l}": ctx.upstream("packaging")[f"thumbnail_{l}"] for l in langs})
        return outputs


def parse_ass(path) -> list[tuple[float, float]]:
    def secs(t: str) -> float:
        h, m, s = t.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Dialogue:") and ",Caption," in line:
            parts = line.split(",", 9)
            events.append((secs(parts[1]), secs(parts[2])))
    return events
