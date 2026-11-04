# GEMINI.md

Developer & agent reference for working in this repository.

## Commands

```sh
uv sync                                            # install deps (Python 3.12+, uv)
uv run pytest -q                                   # engine & pipeline tests (fast, offline)
uv run python -m moderator list                    # workflows and agents found on disk
uv run python -m moderator run niche_discovery     # rank niches, saves channel.yaml after your pick
uv run python -m moderator run youtube_short [-p topic="..."] [-p 'languages=[en, fr]'] [--port 8765] [--no-browser]
uv run python -m moderator run youtube_short --llm claude   # same workflow, text by Claude (your Claude plan, via Claude Code CLI)
uv run python -m moderator run demo                # fake agents: exercises dashboard, retries, revisions
uv run python -m moderator resume runs/<run_id> [--retry-failed]   # continue an interrupted/failed run
uv run python -m moderator run youtube_short --headless -p 'auto_approve=[A, B]'   # scheduled mode, exits at checkpoint C
uv run python -m moderator summary runs/<run_id>   # markdown review summary (used for the GitHub issue)
uv run python -m moderator upload runs/<run_id> --approved-by me --privacy private
uv run python -m moderator youtube-auth --client-secret client_secret.json [--lang en]
uv run python -m moderator optimize-channel --dry-run   # preview channel SEO/banner/playlist changes; drop --dry-run to apply
uv run python -m moderator export-pages _site --repo owner/repo   # static GitHub Pages dashboard export
```

Set `PYTHONIOENCODING=utf-8` when printing Arabic to the Windows console. `moderator/tools/ffmpeg.py` automatically checks `PATH`, Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`), and Windows WinGet folders.

## Architecture

A generic engine runs workflows made of agents; nothing in `moderator/engine/` is specific to YouTube.

- **Workflows** (`workflows/*.yaml`): steps with `agent`, `depends_on`, optional `checkpoint` (`type: approve|choice`, `route_to`) and `with:` options passed to the agent as `ctx.options`. Adding a workflow only needs a YAML file plus agent folders.
- **Agents** (`agents/<name>/agent.yaml` + `handler.py` defining `class Handler(Agent)` with `async run(ctx) -> {output_name: path relative to run folder}`). `strategies` in `agent.yaml` are tried in order on retries (attempt `n` uses `strategies[n]`). Loaded dynamically by `engine/registry.py`.
- **State** (`engine/state.py`): `runs/<run_id>/state.json` is the single source of truth. Only the engine process writes it, through `StateStore.mutate()` (lock + atomic replace). Agents report via `StepContext` (`log`, `progress`, `add_cost`, `offer_choices`, `request_revision`, `upstream(step)`, `decision(cp)`).
- **Orchestrator** (`engine/orchestrator.py`): starts steps whose deps are `done`, runs independent ones in parallel, retries up to `max_retries`, cancels stale parallel tasks on `send_back()`, and sets `waiting_for_approval` at checkpoints.
- **Dashboard** (`server/app.py` + `dashboard/`): FastAPI in the same asyncio loop as the engine. Vanilla JS polls `/api/state` every 3 s, supports switching across past runs via `/api/runs`, and serves run files from `/files/`.
- **Text provider per run**: Gemini (default) or Claude, chosen with `--llm claude`, `-p llm=claude`, env `MODERATOR_LLM` or `config.yaml llm.provider`; stored in the run's params so `resume` keeps it. Workflows and agents are provider-agnostic (`ctx.llm.ask`). Claude (`engine/llm_claude.py`) runs headless Claude Code (`claude -p --json-schema ... --setting-sources ""`) on the user's plan with the same complexity routing (low = haiku, medium = sonnet, high = opus; `llm.claude.tiers`); its costs are notional. Images still use Gemini Nano Banana when `GEMINI_API_KEY` is set, otherwise stock footage.
- **Gemini AI** (`engine/llm.py`): unified `GeminiClient` powered by `GEMINI_API_KEY`:
  - **Model routing by complexity**: each agent declares `complexity: low|medium|high` in `agent.yaml`; `config.yaml` `llm.tiers` maps it to a model and thinking level (low = flash-lite/minimal, medium = flash/low, high = flash/high), and each retry moves one tier up. `ctx.llm.ask(..., complexity=...)` overrides per call. Thinking tokens are counted in the cost. A daily-quota 429 or 404 takes that model out for the rest of the run; 503 and per-minute 429 retry the same model once.
  - **Gemini Flash** (`model: flash` -> `gemini-3.8-flash` with automatic fallback to `gemini-3-flash-preview` / `gemini-2.5-flash`) for reasoning, structured JSON (`responseSchema`), and live web research (`google_search` grounding via `ctx.llm.ask(..., tools=["WebSearch"])`).
  - **Nano Banana** (`image_model: banana` -> `gemini-nano-banana-2.1` with automatic fallback to `gemini-3.1-flash-image` / `gemini-2.5-flash-image`) for native `9:16` vertical scene and thumbnail artwork via `ctx.llm.generate_image(...)`.

## Scheduling and publishing

- `.github/workflows/generate-short.yml` (cron, twice daily) runs headless with `auto_approve=[A, B]`, uploads the run folder as an artifact, commits `history/topics.jsonl`, and opens a `short-review` issue. `upload-short.yml` uploads only when the repo owner comments `/approve` on that issue; that comment is the human approval of checkpoint C. Setup steps are in `docs/SETUP.md`.
- `history/topics.jsonl` (written by the Scriptwriter, read by the Trend Researcher) prevents scheduled runs from repeating topics.

## YouTube Short specifics

- Language settings (dialect instructions, voices, measured words/second) live in `moderator/tools/languages.py` (`en` = English, `fr` = French, `ar` = Egyptian colloquial Arabic). Agents build JSON schemas dynamically over the active `languages` list.
- Visuals: free stock video first (`Pexels`/`Pixabay`/Wikimedia); Nano Banana 9:16 images only for scenes with no usable clip, then stock photo, then procedural gradients. `-p visual_mode=ai` puts Nano Banana first; `-p visual_mode=stock` never uses it ($0).
- Scene timing comes from `edge-tts` word boundaries (`timings_<lang>.json`, with automatic proportional fallback if boundary events are omitted); the editor cuts each scene to that language's narration.
- Copyright: every visual has an entry in `assets/licenses.json`; music/SFX are synthesized or come from `library/music/*.mp3` with a sibling `.json` license file. QA blocks anything unlicensed.
- People rule (`moderator/tools/visual_rules.py`, the only place to edit it): no women or girls in visuals; a face-only close-up is the one exception. The Scriptwriter avoids them in descriptions and search terms, the Visual Producer rewrites female search terms and drops stock results whose tags/slug mention women, image prompts (scenes and thumbnail) carry the rule, and QA inspects 3 frames per scene plus the thumbnails with the LLM. A violation is a blocker that sends only the flagged scenes back to Visual Producer (other scenes are kept) or the thumbnail back to Packaging.

