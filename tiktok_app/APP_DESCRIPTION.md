# TikTok app submission: Moderator Shorts

**Category:** Lifestyle
**Web/App URL:** https://jaleleddineagrebi.github.io/moderator/
**Terms of Service:** https://jaleleddineagrebi.github.io/moderator/docs/terms_of_service.html
**Privacy Policy:** https://jaleleddineagrebi.github.io/moderator/docs/privacy_policy.html
**Icon:** `app_icon_1024.png` (1024x1024) **Demo video:** `demo_video.mp4`

## App name
Moderator Shorts

## Short description (up to ~120 chars)
Create and publish short lifestyle videos to your own TikTok account, with your approval before every post.

## Full description
Moderator Shorts helps a lifestyle creator turn ideas into short vertical videos and publish them to their own TikTok account. The app researches a topic, writes a short script, builds the video (stock footage, voiceover, captions) and prepares a title and hashtags.

Nothing is posted automatically. Every video is first reviewed by the account owner, who approves it explicitly. Only then does the app upload it to the owner's TikTok account through the official TikTok API. The app is used by a single creator for their own account. It does not collect data from other TikTok users and does not read their content.

## Explanation for each product

| Product | Why we need it | How it is used |
|---|---|---|
| **Login Kit** | The creator must authorize the app to act on their own account. | The owner logs in with TikTok once and grants consent. We store only the OAuth access/refresh tokens, as encrypted GitHub secrets. No other profile data is read. |
| **Content Posting API** (Direct Post) | Core feature: publishing the approved video. | After the owner approves a video, the app uploads the MP4 with its title and hashtags to the owner's account. Scope: `video.publish` (and `video.upload` for drafts). |
| **Share Kit** (optional, only if you enable it) | Not required. Leave it off unless TikTok asks. | Would let the owner share a finished video to TikTok from the app. |

Requested scopes: `user.info.basic` (to confirm which account is connected), `video.publish`, `video.upload`.

## Data use and privacy summary
- Only the owner's own account is connected.
- No data about other users is collected or sold.
- Tokens are stored encrypted and can be revoked at any time from TikTok settings.
- Generated videos are kept in private workflow artifacts that expire automatically.

## Notes for the reviewer
The demo video shows: idea and script generation, the finished short, the owner's approval step, TikTok login and consent, and the upload to the owner's account.

