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
