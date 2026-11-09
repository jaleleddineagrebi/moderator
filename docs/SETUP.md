# Setup: GitHub Actions + YouTube Channel Publishing

How the automated pipeline works:
1. **[`generate-short.yml`](../.github/workflows/generate-short.yml)** runs twice daily on cron (or on-demand via **Actions → Generate Short → Run workflow**), executes all 7 agents (`gemini-3.8-flash` + `gemini-nano-banana-2.1` + `edge-tts` + `ffmpeg`), saves the finished `.mp4` Shorts & `.png` thumbnails as a downloadable Action artifact, and opens a GitHub Issue labeled `short-review`.
2. **Human Checkpoint C:** Nothing is ever uploaded to YouTube automatically. Publishing runs **only** when you approve:

| Comment on the `short-review` Issue | Effect |
| :--- | :--- |
| `/approve` | Uploads all generated languages as **private** |
| `/approve unlisted` / `/approve public` | Uploads with that visibility |
| `/approve public en` (or `fr` / `ar`) | Uploads **only** the specified language(s) |
| `/reject` | Closes the issue without uploading anything |
| `/edit ...` | Changes the Short before publishing (see below); the new version is posted on the same issue |

**Edit before publishing** ([`edit-short.yml`](../.github/workflows/edit-short.yml)). Only the step you name and the steps after it are redone, with the same text model as the original run:

| Comment | What is redone |
| :--- | :--- |
| `/edit text make the hook punchier` | Script (narration + captions), then everything after it |
| `/edit first image show a man running at sunrise` | Scene 1 visual only; other scenes are kept |
| `/edit image 3 a calm lake` / `/edit images 2,4 darker city` / `/edit last image` | Those scenes (no description = just a different clip) |
| `/edit images warmer colours` | Every scene visual |
| `/edit title shorter, ask a question` / `/edit thumbnail ...` | Title, description, tags, thumbnail |
| `/edit voice slower` (or `faster`, `different voice`) | Voiceover |
| `/edit music lower` (or `louder`, `hard cuts`, `no sfx`) | Final video mix |

Put several `/edit` lines in one comment to apply them together. When the new version is posted, `/approve` publishes **that** version; you can keep editing as many times as you want.

*(You can also trigger **[`upload-short.yml`](../.github/workflows/upload-short.yml)** manually from the GitHub Actions UI using `run_id` and `gh_run_id`.)*

---

## 1. Authorize Your YouTube Channel (One-Time, Local)

1. **Create a Google Cloud Project:** <https://console.cloud.google.com> → **New Project** (e.g., `moderator-youtube`).
2. **Enable YouTube Data API v3:** **APIs & Services → Library → YouTube Data API v3 → Enable**.
3. **Configure OAuth Consent Screen:**
   - **APIs & Services → OAuth consent screen → External** → enter an app name and your email → add your Google account under **Test users**.
   - Click **Publish App** (move status to *In production*). *(In "Testing" mode, Google expires refresh tokens after 7 days; moving to "In production" keeps your GitHub Actions refresh token working long-term. You will just click "Advanced → Continue" once during local login.)*
4. **Download Desktop OAuth Client JSON:**
   - **APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app**.
   - Download the JSON file into this repo root as `client_secret.json` (git-ignored).
5. **Generate Your Channel Token:**
   - **Option A — Single YouTube Channel (simplest):**
     ```sh
     uv run python -m moderator youtube-auth --client-secret client_secret.json
     ```
     Sign in and pick your YouTube channel (or Brand Account). This creates `tokens/youtube.json` with upload + read-only permission (it cannot edit or delete videos) → store its contents as the GitHub secret **`YOUTUBE_TOKEN`**.
   - **Option B — Separate Channel Per Language (`en`, `fr`, `ar`):**
     ```sh
     uv run python -m moderator youtube-auth --lang en --client-secret client_secret.json
     uv run python -m moderator youtube-auth --lang fr --client-secret client_secret.json
     ```
     Creates `tokens/youtube_en.json` / `tokens/youtube_fr.json` → store as **`YOUTUBE_TOKEN_EN`** / **`YOUTUBE_TOKEN_FR`** (or **`YOUTUBE_TOKEN_AR`**).

---

## 2. Add GitHub Repository Secrets & Variables

In your GitHub repository → **Settings → Secrets and variables → Actions**:

### Secrets (Required & Optional)
| Secret Name | Required? | Value |
| :--- | :---: | :--- |
| `GEMINI_API_KEY` | **Required** | API key from [Google AI Studio](https://aistudio.google.com/apikey) (powers Gemini 3.8 Flash + Nano Banana 2.1) |
| `YOUTUBE_TOKEN` | **Required*** | Entire JSON content of `tokens/youtube.json` (if publishing to **one** YouTube channel) |
| `YOUTUBE_TOKEN_EN` / `FR` / `AR` | *Optional* | Entire JSON content of `tokens/youtube_<lang>.json` (overrides `YOUTUBE_TOKEN` per language) |
| `PIXABAY_API_KEY` | *Recommended* | Instant free key from <https://pixabay.com/api/docs/> (HD live-action stock video clips; \$0) |
| `PEXELS_API_KEY` | *Optional* | Existing key from <https://www.pexels.com/api/> if you have one *(new key issuance is currently paused by Pexels; Wikimedia CC0 + Pixabay cover video automatically)* |
| `YOUTUBE_API_KEY` | *Optional* | Read-only YouTube Data API v3 key for live trend metrics |

### Repository Variables (Optional — under the *Variables* tab)
- `MODERATOR_LANGUAGES`: e.g. `en` (single language) or `en,fr` (default comes from `channel.yaml`)
- `MODERATOR_NICHE`: override the channel niche without editing `channel.yaml`
- `MODERATOR_BUDGET_USD`: per-run spend cap in USD (default `1.00`)
- `MODERATOR_VISUAL_MODE`: `auto` (Nano Banana 2.1) or `stock` (free stock clips first)

---

## 3. Important YouTube API Notes

- **Private-only until Google audit (or flip public in YouTube Studio):** Unverified Google Cloud projects can upload videos via API as **private** immediately; uploading directly as `public` via API requires submitting Google's free [YouTube API Services Audit Form](https://support.google.com/youtube/contact/yt_api_form). Until audited, comment `/approve` (uploads as `private`) and switch visibility to **Public** with one tap in the YouTube Studio mobile/web app!
- **Daily Quota:** Google grants **10,000 free units/day** per Cloud project. Each video upload uses **1,600 units** (up to **6 video uploads/day** free).
- **Custom Thumbnails:** Require a phone-verified YouTube channel (<https://www.youtube.com/verify>).

---

## 4. Test End-to-End on GitHub

1. Push this repository to GitHub (`git push origin main`).
2. Open **Actions → Generate Short → Run workflow** (optionally enter a `topic` and `languages: en`).
3. When the `short-review` issue opens (~3–6 minutes), download the `short-<run_id>` artifact to preview the `.mp4` Short, then comment `/approve` on the issue to publish it to your YouTube channel!

---

## 5. Enable GitHub Pages Live Agent Dashboard

Every push to `main`, `Generate Short` run (streaming every 15 seconds while agents execute!), and `Upload Short` run automatically updates a **`gh-pages`** branch with the full Moderator Dashboard UI, agent progress, thumbnails, playable `.mp4` Shorts, QA reports, and published YouTube links.

To turn on the public dashboard URL once after your first push:
1. Go to your repo **Settings → Pages**.
2. Under **Build and deployment → Source**, keep **Deploy from a branch** and select **`gh-pages`** / **`/ (root)`** → **Save**.
3. Open **`https://<your-username>.github.io/<repo-name>/`**!

---

## 6. Optimize the YouTube Channel (One-Time, Local)

`optimize-channel` sets the channel description, keywords, language and country, uploads a 2560x1440 banner, creates a public Shorts playlist with every upload, and adds `#shorts` plus a comment question (in each video's language) to existing Shorts. The copy depends on `--preset` (`auto` picks from the channel title and `channel.yaml`'s niche; or `psychology`, `ai`, `hybrid`).

Preview first. Nothing is written to YouTube; the banner is saved to `runs/channel_banner.jpg`:

```sh
uv run python -m moderator optimize-channel --dry-run
```

Then apply it. The first time, a browser opens to grant full channel-management permission. That token is saved separately as `tokens/youtube_manage.json` and stays on this machine: never store it as a GitHub secret (the upload token is enough there).

```sh
uv run python -m moderator optimize-channel --preset auto --country US --lang en
```

The API cannot change the channel name or `@handle`; the command prints a suggestion to apply in **YouTube Studio → Customization**.

---

## 7. Use Claude Instead of Gemini on GitHub

The same `Generate Short` workflow can write with Claude (Haiku / Sonnet / Opus routed by task complexity) through the Claude Code CLI on your Claude plan.

1. On your computer, create a long-lived token for CI (opens the browser once):
   ```sh
   claude setup-token
   ```
2. In GitHub → **Settings → Secrets and variables → Actions → Secrets**, add **`CLAUDE_CODE_OAUTH_TOKEN`** with that token. (Or `ANTHROPIC_API_KEY` to pay per token through the API instead of your plan.)
3. Run it:
   - **Once:** **Actions → Generate Short → Run workflow**, set **llm** to `claude`.
   - **Every scheduled run:** add the repository **variable** `MODERATOR_LLM` = `claude` (Variables tab). Remove it to go back to Gemini.
4. Keep `GEMINI_API_KEY` if you want AI-generated images (Claude cannot make images); without it, visuals use stock footage only.

Publishing is unchanged: comment `/approve` on the `short-review` issue and `Upload Short` uploads to YouTube.

---

## 8. Protect `main` (Pull Requests Only)

[`.github/rulesets/protect-main.json`](../.github/rulesets/protect-main.json) blocks direct pushes to `main`:

- every change goes through a pull request, and the `test` CI check must pass before it can be merged
- force-pushes and deleting `main` are blocked
- only people with write access (you and the collaborators you invite) can merge
- there are no exceptions, not even for you or the GitHub Actions bot. Scheduled runs save their topic history to the separate `topics-history` branch instead of `main`, so a run never repeats a topic and never conflicts with your PRs.

To see GitHub's topics on this PC before a local run: `git fetch origin topics-history && git show origin/topics-history:topics.jsonl > history/topics.jsonl`

To turn it on:

1. Go to GitHub → **Settings → Rules → Rulesets → New ruleset → Import a ruleset**.
2. Pick `.github/rulesets/protect-main.json`, then click **Create**.

Then, under **Settings → Actions → General**:

- set **Approval for running fork pull request workflows from contributors** to **Require approval for all external contributors**, so outsiders' PRs never run workflows without your OK
- keep **Workflow permissions** at *Read repository contents* (each workflow asks for the extra permissions it needs)

Only you and your collaborators can use `/approve`, `/edit` and `/reject` on review issues, and only they can click **Run workflow**. Comments from anyone else are ignored.

## TikTok (optional)

Posting uses the official Content Posting API. It runs after YouTube in `Upload Short`, only for runs a human approved, and is skipped when no TikTok secret exists.

1. In the TikTok developer portal, add **Login Kit** and **Content Posting API** to your app, request the scopes `user.info.basic`, `video.upload`, `video.publish`, and register a **redirect URI** (any https page you control, e.g. `https://<user>.github.io/<repo>/`).
2. Locally: `export TIKTOK_CLIENT_KEY=... TIKTOK_CLIENT_SECRET=...` then `uv run python -m moderator tiktok-auth --redirect-uri <that URI>`. Log in with the publishing account, then paste back the address you were redirected to. The token is saved to `tokens/tiktok.json`.
3. GitHub secrets: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, and `TIKTOK_TOKEN` (the whole `tokens/tiktok.json`). Use `TIKTOK_TOKEN_EN/FR/AR` for one account per language.
4. Manual post of an approved run: `uv run python -m moderator upload-tiktok runs/<run_id> --privacy private`.

Until TikTok audits your app, TikTok forces every post to private (`SELF_ONLY`). The refresh token lasts about a year, so repeat step 2 and update the secret then.

---

## 9. Daily Portal Posts (Database, Companion Shorts, Pull Request)

[`daily-portal-content.yml`](../.github/workflows/daily-portal-content.yml) writes two articles twice a day, saves them to the portal database, and opens a pull request with them.

**Repository secrets and variables**

| Name | Kind | Used for |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | secret | Writing the articles (always the cheapest model) |
| `PORTAL_API_ENDPOINT` | secret | The portal URL, e.g. `https://your-portal.vercel.app`. The pipeline posts each article to `<endpoint>/api/posts`. |
| `INTERNAL_API_SECRET` | secret | Must equal `INTERNAL_API_SECRET` in the portal's Vercel environment variables |
| `YOUTUBE_API_KEY` | secret | Finds your real, public Shorts so articles link to a playable video |
| `YOUTUBE_CHANNEL_ID` | variable (optional) | Channel ID starting with `UC` (or an `@handle`). Defaults to the "land of ai" channel. |

- **The run fails if the database save fails**, or if `PORTAL_API_ENDPOINT` / `INTERNAL_API_SECRET` are missing. The job summary lists every post with its Short and whether it was saved.
- **Companion Shorts:** only public, embeddable videos of the channel are linked, and each Short is used by one article. Private or unlisted Shorts are skipped. Without `YOUTUBE_API_KEY`, articles are published without a video.
- **Pull request:** each run pushes a `daily-posts/<date>` branch with `history/daily_posts/<date_time>.json` and opens a PR. For the PR to open, turn on **Settings → Actions → General → Workflow permissions → "Allow GitHub Actions to create and approve pull requests"**. Without it the run prints a link to open the PR yourself. The workflow also starts the `CI & Pages` workflow on the branch, because a PR opened by Actions does not start CI and your `main` ruleset requires the `test` check.
- **Duplicate topics:** the archive is also kept on the `portal-history` branch, so the next run avoids topics even before you merge the PR.

**Cleaning old fake Shorts.** Early seed data stored run folder names as YouTube IDs. The portal now hides any Short whose ID is not a real 11-character video ID. To remove them from the database too, run once in the Supabase / Postgres SQL editor:

```sql
UPDATE "Post" SET "youtubeShortId" = NULL WHERE "youtubeShortId" IS NOT NULL AND "youtubeShortId" !~ '^[A-Za-z0-9_-]{11}$';
DELETE FROM "YouTubeShort" WHERE id !~ '^[A-Za-z0-9_-]{11}$';
```
