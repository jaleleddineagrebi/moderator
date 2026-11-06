"""YouTube channel growth & SEO optimizer via official YouTube Data API v3.

Automates everything Google allows via API:
1. Channel description, 500-char SEO keywords, defaultLanguage & tier-1 country targeting (`channels.update`)
2. Custom 2560x1440 UHD channel banner rendered inside the 1546x423 mobile safe zone (`channelBanners.insert`)
3. Public Shorts binge playlist containing all uploaded Shorts (`playlists.insert` + `playlistItems.insert`)
4. Retroactive SEO optimization of existing uploaded Shorts (`videos.update`: `#shorts` title tag + comment-hook)

Note: Google permanently restricts changing the Channel Name and `@handle` via API for anti-hijack security;
those two fields are updated manually in YouTube Studio -> Customization.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import urllib3.util.connection
import yaml
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from PIL import Image, ImageDraw, ImageFilter

from .. import ROOT
from . import text, youtube_upload

MANAGE_SCOPE = "https://www.googleapis.com/auth/youtube"


_ORIG_GETADDRINFO = socket.getaddrinfo


def _ipv4_getaddrinfo(host, port, family=0, *args, **kwargs):
    if host in ("localhost", "127.0.0.1", "::1", None, ""):
        return _ORIG_GETADDRINFO(host, port, family, *args, **kwargs)
    return _ORIG_GETADDRINFO(host, port, socket.AF_INET, *args, **kwargs)


def _prefer_ipv4(set_timeout: bool = True) -> None:
    """Avoid broken local IPv6 routes stalling requests/httplib2 calls to *.googleapis.com."""
    if set_timeout:
        socket.setdefaulttimeout(60)
    urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET
    socket.getaddrinfo = _ipv4_getaddrinfo


def format_channel_keywords(phrases: list[str], max_chars: int = 480) -> str:
    """Format YouTube brandingSettings.channel.keywords (space-separated, multi-word terms quoted, <=500 chars)."""
    tokens: list[str] = []
    total = 0
    seen: set[str] = set()
    for raw in phrases:
        clean = " ".join(raw.replace('"', "").split()).strip()
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        tok = f'"{clean}"' if " " in clean else clean
        added = len(tok) + (1 if tokens else 0)
        if total + added > max_chars:
            break
        tokens.append(tok)
        total += added
    return " ".join(tokens)


def build_channel_profile(
    preset: str = "auto",
    channel_title: str = "",
    channel_cfg: dict | None = None,
    country: str = "US",
    default_language: str = "en",
) -> dict:
    cfg = channel_cfg or {}
    niche = str(cfg.get("niche") or "Psychology & human behavior")
    title_low = (channel_title or "").lower()
    if channel_title and channel_title.islower():  # "land of ai" -> "Land of AI" for the description
        small = {"of", "and", "the", "a", "an", "in", "on", "for", "to"}
        channel_title = " ".join(
            w.upper() if w in ("ai", "ia") else w if i and w in small else w.capitalize()
            for i, w in enumerate(channel_title.split())
        )
    mode = preset.lower()
    if mode == "auto":
        if "ai" in title_low and "psych" in niche.lower():
            mode = "hybrid"
        elif "ai" in niche.lower() or ("ai" in title_low and not cfg):
            mode = "ai"
        else:
            mode = "psychology"

    if mode == "ai":
        headline = (channel_title or "LAND OF AI").upper()
        subtitle = "DAILY AI BREAKTHROUGHS · FUTURE TECH · MIND-BLOWING TOOLS"
        description = (
            "Welcome to Land of AI — fast, visual 40-second Shorts breaking down the wildest AI breakthroughs, "
            "hidden tools, robotics, and how artificial intelligence is reshaping human life.\n\n"
            "⚡ New Shorts every day: zero fluff, real science, instant takeaways.\n"
            "🔔 Subscribe so you never miss the next breakthrough.\n\n"
            "#Shorts #AI #ArtificialIntelligence #FutureTech #TechFacts"
        )
        kw_list = [
            "artificial intelligence", "ai shorts", "ai tools", "future technology", "tech facts",
            "machine learning", "chatgpt", "robotics", "science facts", "mind blowing tech",
            "daily shorts", "ai news", "brain and ai", "automation", "tech explained", "shorts",
        ]
        playlist_title = "Mind-Blowing AI & Future Tech Shorts"
        playlist_desc = "Bite-sized daily Shorts on AI breakthroughs, hidden tools, and the future."
        studio_tip = "Recommended @handle in YouTube Studio -> Customization: @LandOfAIShorts (instead of @bbw-e7w)."
    elif mode == "hybrid":
        headline = (channel_title or "LAND OF AI & MIND").upper()
        subtitle = "HUMAN PSYCHOLOGY · BRAIN BIAS CHECKS · AI & BEHAVIOR"
        description = (
            f"Welcome to {channel_title or 'Land of AI'} — daily bite-sized Shorts decoding human psychology, "
            "cognitive biases, brain hacks, and how modern technology & AI shape the way you think and act.\n\n"
            "🧠 Understand your mind in under 45 seconds a day.\n"
            "⚡ Follow for a daily brain bias check & psychology insights!\n\n"
            "#Shorts #Psychology #HumanBehavior #Mindset #BrainFacts #AI"
        )
        kw_list = [
            "psychology", "psychology facts", "human behavior", "mindset", "cognitive biases",
            "brain facts", "social anxiety", "habits", "dopamine", "self improvement",
            "artificial intelligence", "mind hacks", "body language", "social dynamics",
            "psychology shorts", "shorts",
        ]
        playlist_title = "Human Mind, Psychology & Brain Hacks (Shorts)"
        playlist_desc = "Fast daily Shorts explaining why your brain does what it does — biases, habits, and mindset."
        studio_tip = (
            "Recommended in YouTube Studio -> Customization: change handle from @bbw-e7w to @MindDecodedAI "
            "(or rename channel to 'Mind Decoded' / '@MindDecodedShorts' for pure psychology)."
        )
    else:
        headline = "MIND DECODED"
        subtitle = "DAILY PSYCHOLOGY · BRAIN BIAS CHECKS · HUMAN BEHAVIOR"
        description = (
            "Why does your brain remember embarrassing moments for years, fall for manipulation, or crave dopamine?\n\n"
            "Every day we break down real psychology, cognitive biases, habits, and social dynamics in under 45 seconds "
            "— backed by behavioral science and zero fluff.\n\n"
            "🧠 Follow for a daily brain bias check & mindset breakdowns!\n\n"
            "#Shorts #Psychology #HumanBehavior #Mindset #SelfImprovement #BrainFacts"
        )
        kw_list = [
            "psychology", "psychology facts", "human behavior", "cognitive biases", "mindset",
            "brain facts", "social dynamics", "habits", "procrastination", "spotlight effect",
            "dopamine detox", "self improvement", "social anxiety", "mind hacks", "psychology shorts", "shorts",
        ]
        playlist_title = "Psychology & Human Behavior — Best Shorts"
        playlist_desc = "Curiosity-driven Shorts explaining cognitive biases, habits, and human behavior."
        studio_tip = (
            "Recommended in YouTube Studio -> Customization: rename channel from 'land of ai' to 'Mind Decoded' "
            "(or 'Brain & Behavior') and change handle from @bbw-e7w to @MindDecodedShorts."
        )

    return {
        "mode": mode,
        "description": description[:990],
        "keywords": format_channel_keywords(kw_list),
        "default_language": default_language,
        "country": country.upper(),
        "banner_headline": headline[:28],
        "banner_subtitle": subtitle[:64],
        "playlist_title": playlist_title,
        "playlist_description": playlist_desc,
        "studio_tip": studio_tip,
    }


def render_channel_banner(dest: Path, headline: str, subtitle: str, badge: str = "NEW SHORTS DAILY") -> Path:
    """Render a 2560x1440 UHD YouTube banner with all text strictly inside the centered 1546x423 safe zone."""
    w, h = 2560, 1440
    img = Image.new("RGB", (w, h), (10, 12, 22))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        r = int(10 * (1 - t) + 18 * t)
        g = int(14 * (1 - t) + 22 * t)
        b = int(28 * (1 - t) + 44 * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    glow = Image.new("RGB", (w, h), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([480, 260, 1420, 1180], fill=(0, 165, 215))
    gd.ellipse([1180, 280, 2100, 1160], fill=(235, 175, 20))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(180)), 0.24)

    draw = ImageDraw.Draw(img)
    # Subtle accent frame inside safe zone (x: 507..2053, y: 508..931)
    pill_w, pill_h = 430, 56
    px0, py0 = (w - pill_w) // 2, 548
    draw.rounded_rectangle([px0, py0, px0 + pill_w, py0 + pill_h], radius=28, fill=(255, 214, 10))
    badge_font = text.font("en", 28)
    bw = draw.textlength(badge, font=badge_font)
    draw.text(((w - bw) / 2, py0 + 11), badge, font=badge_font, fill=(12, 14, 22))

    # Main channel headline centered at y=700 (well inside 508..931)
    text.draw_block(
        img,
        headline,
        "en",
        size=108,
        y_center=705,
        max_width=1460,
        fill=(255, 255, 255),
        stroke=(8, 10, 18),
        stroke_width=8,
    )
    # Subtitle centered at y=835 (well inside 508..931)
    text.draw_block(
        img,
        subtitle,
        "en",
        size=34,
        y_center=838,
        max_width=1460,
        fill=(120, 232, 255),
        stroke=(8, 10, 18),
        stroke_width=4,
    )

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="JPEG", quality=92, optimize=True)
    return dest


# Line 1 of a Short's description: a question that invites comments, written per video language
COMMENT_HOOKS = {
    "en": "Has this ever happened to you? Tell me in the comments 👇",
    "fr": "Ça t'est déjà arrivé ? Raconte-moi en commentaire 👇",
    "ar": "حصلك قبل كده؟ احكيلنا في الكومنتات 👇",
}


def manage_token_path(lang: str) -> Path:
    """Local-only token with full channel-management scope, kept apart from the upload token (the GitHub secret)."""
    if (youtube_upload.TOKENS_DIR / f"youtube_{lang.lower()}.json").exists():
        return youtube_upload.TOKENS_DIR / f"youtube_manage_{lang.lower()}.json"
    return youtube_upload.MANAGE_TOKEN


def token_has_manage_scope(lang: str = "en") -> bool:
    path = manage_token_path(lang)
    if not path.exists():
        return False
    scopes = json.loads(path.read_text(encoding="utf-8")).get("scopes") or []
    return MANAGE_SCOPE in scopes or "https://www.googleapis.com/auth/youtube.force-ssl" in scopes


def plan_video_update(snippet: dict, fallback_lang: str = "en") -> dict | None:
    """New title/description for an uploaded Short, or None when it is already optimized.
    The comment hook is written in the video's own language; unknown languages keep their description."""
    title = snippet["title"]
    desc = snippet.get("description", "")
    new_title = title
    if "#shorts" not in title.lower() and len(title.rstrip()) <= 91:
        new_title = f"{title.rstrip()} #shorts"
    lang = (snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage") or fallback_lang).split("-")[0].lower()
    hook = COMMENT_HOOKS.get(lang)
    first_line = desc.splitlines()[0] if desc else ""
    new_desc = desc
    if hook and "?" not in first_line and "؟" not in first_line:
        new_desc = f"{hook}\n\n{desc}".strip()
    if new_title == title and new_desc == desc:
        return None
    return {"title": new_title[:100], "description": new_desc[:4900]}


def optimize_channel(
    *,
    lang: str = "en",
    preset: str = "auto",
    country: str = "US",
    client_secret: Path | None = None,
    reauth: bool = False,
    banner_out: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """Apply channel SEO, 2560x1440 banner, Shorts binge playlist, and existing video title/description upgrades.
    With dry_run, only reads the channel and renders the banner: nothing is written to YouTube."""
    _prefer_ipv4(set_timeout=False)
    socket.gethostbyname("www.googleapis.com")
    manage_path = manage_token_path(lang)
    if reauth or not token_has_manage_scope(lang):
        secret_path = client_secret or (ROOT / "client_secret.json")
        if not secret_path.exists():
            raise RuntimeError(
                f"Channel optimization needs a token with '{MANAGE_SCOPE}' ({manage_path} is missing). "
                f"Pass --client-secret client_secret.json to authorize once."
            )
        print("Opening browser to grant YouTube channel-management permission (one-time, stays on this machine)...",
              flush=True)
        youtube_upload.authorize(secret_path, scopes=youtube_upload.MANAGE_SCOPES, path=manage_path)
    _prefer_ipv4(set_timeout=True)

    creds = youtube_upload.credentials_from_file(manage_path)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    ch_resp = yt.channels().list(part="snippet,brandingSettings,contentDetails,statistics", mine=True).execute()
    items = ch_resp.get("items", [])
    if not items:
        raise RuntimeError("No YouTube channel found on the authenticated Google account.")
    ch = items[0]
    channel_id = ch["id"]
    current_title = ch["snippet"]["title"]
    custom_url = ch["snippet"].get("customUrl", "")

    cfg_path = ROOT / "channel.yaml"
    channel_cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    profile = build_channel_profile(
        preset=preset,
        channel_title=current_title,
        channel_cfg=channel_cfg,
        country=country,
        default_language=lang,
    )

    # 1. Render and upload 2560x1440 UHD channel banner
    banner_path = banner_out or (ROOT / "runs" / "channel_banner.jpg")
    render_channel_banner(banner_path, profile["banner_headline"], profile["banner_subtitle"])
    result = {
        "channel_id": channel_id,
        "channel_url": f"https://www.youtube.com/channel/{channel_id}",
        "current_title": current_title,
        "current_handle": custom_url,
        "mode": profile["mode"],
        "country": profile["country"],
        "default_language": profile["default_language"],
        "description": profile["description"],
        "keywords": profile["keywords"],
        "banner_path": str(banner_path),
        "studio_tip": profile["studio_tip"],
        "dry_run": dry_run,
    }
    uploads_pid = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    up_items = yt.playlistItems().list(part="contentDetails", playlistId=uploads_pid, maxResults=50).execute().get("items", [])
    video_ids = [u["contentDetails"]["videoId"] for u in up_items]
    videos = yt.videos().list(part="snippet,status", id=",".join(video_ids)).execute().get("items", []) if video_ids else []
    plans = {v["id"]: plan_video_update(v["snippet"], lang) for v in videos}
    result["video_changes"] = {vid: {"from": next(v["snippet"]["title"] for v in videos if v["id"] == vid), **plan}
                               for vid, plan in plans.items() if plan}
    if dry_run:
        result["playlist_url"] = None
        result["updated_videos"] = []
        return result

    banner_res = yt.channelBanners().insert(
        media_body=MediaFileUpload(str(banner_path), mimetype="image/jpeg", resumable=True)
    ).execute()
    banner_url = banner_res["url"]

    # 2. Update channel brandingSettings (description, keywords, defaultLanguage, country, bannerExternalUrl)
    branding = ch.get("brandingSettings") or {}
    ch_brand = branding.get("channel") or {}
    ch_brand["description"] = profile["description"]
    ch_brand["keywords"] = profile["keywords"]
    ch_brand["defaultLanguage"] = profile["default_language"]
    ch_brand["country"] = profile["country"]
    branding["channel"] = ch_brand
    branding.setdefault("image", {})["bannerExternalUrl"] = banner_url

    yt.channels().update(
        part="brandingSettings",
        body={"id": channel_id, "brandingSettings": branding},
    ).execute()

    # 3. Ensure featured Shorts playlist exists & populate with uploaded Shorts
    existing_pls = yt.playlists().list(part="snippet,status", mine=True, maxResults=25).execute().get("items", [])
    playlist = next((p for p in existing_pls if "shorts" in p["snippet"]["title"].lower()), None)
    if not playlist:
        playlist = yt.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": profile["playlist_title"],
                    "description": profile["playlist_description"],
                    "defaultLanguage": profile["default_language"],
                },
                "status": {"privacyStatus": "public"},
            },
        ).execute()
    playlist_id = playlist["id"]
    existing_pl_vids = {
        it["contentDetails"]["videoId"]
        for it in yt.playlistItems().list(part="contentDetails", playlistId=playlist_id, maxResults=50).execute().get("items", [])
    }

    # 4. Add every upload to the playlist and apply the planned title/description changes
    updated_videos: list[str] = []
    for v in videos:
        vid = v["id"]
        if vid not in existing_pl_vids:
            yt.playlistItems().insert(
                part="snippet",
                body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": vid}}},
            ).execute()
        plan = plans.get(vid)
        if plan:
            snip = v["snippet"]
            snip.update(plan)
            snip["categoryId"] = snip.get("categoryId") or youtube_upload.EDUCATION_CATEGORY
            yt.videos().update(part="snippet", body={"id": vid, "snippet": snip}).execute()
            updated_videos.append(vid)

    result["playlist_url"] = f"https://www.youtube.com/playlist?list={playlist_id}"
    result["updated_videos"] = updated_videos
    return result
