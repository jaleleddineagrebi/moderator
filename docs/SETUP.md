# Setup: scheduled Shorts on GitHub Actions + YouTube upload

How it works: `generate-short.yml` runs twice a day, builds both Shorts (Egyptian Arabic + French) and opens an
issue labelled `short-review`. Nothing is published until **you** comment on that issue:

| Comment | Effect |
|---|---|
| `/approve` | uploads both videos as **private** |
| `/approve unlisted` / `/approve public` | uploads with that visibility |
| `/reject` | closes the issue, uploads nothing |

Only the repository owner's comments are accepted. Videos stay downloadable as a run artifact for 14 days.

## 1. Repository secrets

GitHub repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Where it comes from |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | run `claude setup-token` on your PC (uses your Claude plan) |
| `PIXABAY_API_KEY` | your `.env` |
| `PEXELS_API_KEY` | optional, https://www.pexels.com/api/ (better vertical footage) |
| `YOUTUBE_API_KEY` | optional, read-only trend data (step 2.3) |
| `YOUTUBE_TOKEN_AR` | content of `tokens/youtube_ar.json` (step 2.5) |
| `YOUTUBE_TOKEN_FR` | content of `tokens/youtube_fr.json` (step 2.5) |

## 2. YouTube upload access (one-time)

1. **Two channels.** In YouTube, create a channel per language (Settings → Add or manage channels → Create a channel).
   Brand-account channels are fine; you pick which one during authorization.
2. **Google Cloud project.** https://console.cloud.google.com → New project (e.g. "moderator").
3. **Enable the API.** APIs & Services → Library → *YouTube Data API v3* → Enable.
   (Optional: Credentials → Create credentials → API key, restrict it to YouTube Data API v3 → that's `YOUTUBE_API_KEY`.)
4. **OAuth consent + client.**
   - APIs & Services → OAuth consent screen → External → app name, your email → add yourself under *Test users*.
   - Then **Publish app** (move it to *In production*). In *Testing* mode Google expires refresh tokens after 7 days,
     which would break the scheduled uploads. An unverified app in production only shows a warning screen to you.
   - Credentials → Create credentials → OAuth client ID → **Desktop app** → download the JSON as `client_secret.json`
     into this folder (it is git-ignored).
5. **Authorize each channel** (opens the browser; choose the matching channel on the account picker):
   ```sh
   uv run python -m moderator youtube-auth --lang ar --client-secret client_secret.json
   uv run python -m moderator youtube-auth --lang fr --client-secret client_secret.json
   ```
   Each prints the channel name it is bound to. Copy each `tokens/youtube_<lang>.json` into the matching secret.

### Limits to know

- **Private-only until audit.** Videos uploaded through the API by an *unverified* Google Cloud project are locked to
  private. To publish publicly, submit the free YouTube API Services audit form
  (https://support.google.com/youtube/contact/yt_api_form). Until it is approved, use `/approve` (private) and the
  videos wait in YouTube Studio.
- **Quota.** 10,000 units/day per project; one upload costs 1,600, so 2 runs × 2 languages = 6,400/day fits.
- **Thumbnails** need a phone-verified channel (youtube.com/verify). Shorts feeds often show a video frame anyway.

## 3. GitHub Actions costs

Private repos get 2,000 free Action minutes/month. A run takes roughly 15–25 minutes, so two a day uses
~900–1,500 minutes. Check usage in Settings → Billing. Change the times in `.github/workflows/generate-short.yml` (`cron`, UTC).

## 4. Trying it

Actions tab → *Generate Short* → *Run workflow* (optional topic). When the issue appears, download the artifact,
watch `final_short_ar.mp4` / `final_short_fr.mp4`, then comment `/approve`.
