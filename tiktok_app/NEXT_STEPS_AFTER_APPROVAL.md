# TikTok Setup: Steps Once Your App Is Approved

Keep this file as a reference. Once TikTok approves your initial app submission, follow these exact steps to complete the automated publishing setup.

---

### Step 1: Add Content Posting API to your App
1. Go to [TikTok Developer Portal](https://developers.tiktok.com/) and open your **Moderator Shorts** app.
2. In the left menu, click **Products** (or **+ Add Products**).
3. Find **Content Posting API** and click **Add** / **Apply**.
4. Ensure the following permissions / scopes are requested:
   - `video.publish`
   - `video.upload`
   - `user.info.profile` (or `user.info.basic`)
5. Make sure your **Redirect URI** is registered in the app settings:
   ```text
   https://jaleleddineagrebi.github.io/moderator/
   ```

---

### Step 2: Retrieve your App Credentials
In your app's dashboard:
1. Copy your **Client Key**
2. Copy your **Client Secret**

---

### Step 3: Authorize your Account Locally (One-Time)
Open your terminal in this repository and run:

```bash
# 1. Export your app credentials
export TIKTOK_CLIENT_KEY="<your_client_key>"
export TIKTOK_CLIENT_SECRET="<your_client_secret>"

# 2. Run the authentication tool
uv run python -m moderator tiktok-auth --redirect-uri https://jaleleddineagrebi.github.io/moderator/
```

What will happen:
1. The tool prints a TikTok authorization URL.
2. Open that URL in your browser, log into the TikTok account that will host the videos, and click **Authorize**.
3. You will be redirected to `https://jaleleddineagrebi.github.io/moderator/?code=...`.
4. Copy the entire redirected URL from your browser's address bar and paste it back into your terminal prompt.
5. The tool exchanges the code for tokens and saves them locally to:
   ```text
   tokens/tiktok.json
   ```

---

### Step 4: Add GitHub Repository Secrets
Go to your GitHub repo: **Settings ➔ Secrets and variables ➔ Actions ➔ New repository secret** and add these 3 secrets:

| Secret Name | Value |
| :--- | :--- |
| `TIKTOK_CLIENT_KEY` | Your TikTok Client Key |
| `TIKTOK_CLIENT_SECRET` | Your TikTok Client Secret |
| `TIKTOK_TOKEN` | The **entire contents** of `tokens/tiktok.json` |

*(If you have separate TikTok channels per language, you can also use `TIKTOK_TOKEN_EN`, `TIKTOK_TOKEN_FR`, etc.)*

---

### Step 5: Test the Integration
You can test posting an approved run manually from your terminal:

```bash
uv run python -m moderator upload-tiktok runs/<run_id> --privacy private
```

Or simply use the normal GitHub workflow:
When the `Generate Short` workflow opens a review issue, reply with:
```text
/approve
```
The GitHub Action will automatically publish the short to **both YouTube and TikTok**!
