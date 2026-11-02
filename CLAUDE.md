# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```sh
uv sync                                            # install deps (Python 3.12, uv)
uv run pytest -q                                   # engine tests (fast, no network, no Claude calls)
uv run pytest tests/test_engine.py::test_cycle_is_rejected   # single test
uv run python -m moderator list                    # workflows and agents found on disk
uv run python -m moderator run niche_discovery     # rank niches, saves channel.yaml after your pick
uv run python -m moderator run youtube_short [-p topic="..."] [--port 8765] [--no-browser]
uv run python -m moderator run demo                # fake agents: exercises dashboard, retries, revisions
uv run python -m moderator resume runs/<run_id>    # continue an interrupted run
uv run python -m moderator run youtube_short --headless -p 'auto_approve=[A, B]'   # scheduled mode, exits at checkpoint C
uv run python -m moderator summary runs/<run_id>   # markdown review summary (used for the GitHub issue)
uv run python -m moderator upload runs/<run_id> --approved-by me --privacy private
uv run python -m moderator youtube-auth --lang ar --client-secret client_secret.json
```

Set `PYTHONIOENCODING=utf-8` when printing Arabic to the Windows console. ffmpeg comes from `winget install Gyan.FFmpeg`; `moderator/tools/ffmpeg.py` also finds it in the winget package folder when PATH is stale.

## Architecture

A generic engine runs workflows made of agents; nothing in `moderator/` is specific to YouTube.

- **Workflows** (`workflows/*.yaml`): steps with `agent`, `depends_on`, optional `checkpoint` (`type: approve|choice`, `route_to`) and `with:` options passed to the agent as `ctx.options`. Adding a workflow should only need a YAML file plus agent folders.
- **Agents** (`agents/<name>/agent.yaml` + `handler.py` defining `class Handler(Agent)` with `async run(ctx) -> {output_name: path relative to run folder}`). `strategies` in agent.yaml are tried in order on retries (attempt n uses strategies[n]); that is how a retry "changes approach". Loaded dynamically by `engine/registry.py`.
- **State** (`engine/state.py`): `runs/<run_id>/state.json` is the single source of truth. Only the engine process writes it, through `StateStore.mutate()` (lock + atomic replace). Agents report via `StepContext` (`log`, `progress`, `add_cost`, `offer_choices`, `request_revision`, `upstream(step)`, `decision(cp)`).
- **Orchestrator** (`engine/orchestrator.py`): starts steps whose deps are `done`, runs independent ones in parallel, retries up to `max_retries`, sets `waiting_for_approval` at checkpoints. `send_back()` marks a step `needs_revision` with feedback and requeues everything downstream; reviewer revisions are capped by `max_revision_rounds`.
- **Dashboard** (`server/app.py` + `dashboard/`): FastAPI in the same asyncio loop as the engine (state-changing endpoints must stay `async def` so `wake.set()` runs on the loop). Vanilla JS polls `/api/state` every 3 s; run files are served from `/files/`.
- **Claude** (`engine/llm.py`): calls headless Claude Code (`claude -p --output-format json --json-schema ...`) so it runs on the user's Claude plan with no API key. Costs shown are notional. Use `ctx.llm.ask(prompt, schema=..., tools=["WebSearch","WebFetch"])` and include `ctx.revision_notes()` in prompts.

## Scheduling and publishing

- `.github/workflows/generate-short.yml` (cron, twice daily) runs headless with `auto_approve=[A, B]`, uploads the run folder as an artifact, commits `history/topics.jsonl`, and opens a `short-review` issue. `upload-short.yml` uploads only when the repo owner comments `/approve` on that issue; that comment is the human approval of checkpoint C. Setup steps are in `docs/SETUP.md`.
- `Orchestrator.run(headless=True)` returns `"waiting"` / `"failed"` / `"done"`; `params.auto_approve` lists checkpoints approved automatically (a choice takes the top-ranked option).
- `history/topics.jsonl` (written by the Scriptwriter, read by the Trend Researcher) stops scheduled runs repeating topics.

## YouTube Short specifics

- Language settings (dialect instructions, voices, measured words/second) live only in `moderator/tools/languages.py`; agents read them from there. `ar` is Egyptian colloquial Arabic, `fr` is French.
- One script, two languages: every text field is `{ "ar": ..., "fr": ... }`. Visuals are shared; each language gets its own voiceover, captions, timing, video and thumbnail (`final_short_<lang>.mp4`).
- Scene timing comes from edge-tts word boundaries (`timings_<lang>.json`); the editor cuts each scene to that language's narration.
- Arabic text: libass (ffmpeg) shapes it in captions; Pillow does not (no libraqm), so thumbnails go through `tools/text.visual()` (arabic-reshaper + python-bidi). Fonts are Noto (OFL) in `library/fonts/`.
- Copyright: every visual must have an entry in `assets/licenses.json`; music/SFX are generated or come from `library/music/*.mp3` with a sibling `.json` license file. QA blocks anything unlicensed.
- Uploads happen only through `moderator upload` (`moderator/publish.py`), which records who approved checkpoint C. API uploads from an unverified Google project are private-only until YouTube's audit.
- Free API keys (Pexels, Pixabay, YouTube Data) live in `.env` (see `.env.example`); agents degrade gracefully without them (generated backgrounds, web-only research).
