import os
import pickle
import threading
from typing import Optional, Dict, Any

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly'
]

TOKEN_PATH = os.path.join(os.path.dirname(__file__), 'token.pickle')
CLIENT_SECRET_PATH = os.path.join(os.path.dirname(__file__), 'client_secret.json')


def get_credentials(allow_interactive: bool = False):
    """Retrieves valid YouTube OAuth credentials if available."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        try:
            with open(TOKEN_PATH, 'rb') as token:
                creds = pickle.load(token)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, 'wb') as token:
                pickle.dump(creds, token)
            return creds
        except Exception as e:
            print(f"[YouTube Auth] Refresh token error: {e}")
            creds = None

    if allow_interactive:
        if not os.path.exists(CLIENT_SECRET_PATH):
            raise FileNotFoundError("client_secret.json is missing in backend directory!")
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)
        return creds

    return None


def get_authenticated_service(allow_interactive: bool = False):
    creds = get_credentials(allow_interactive=allow_interactive)
    if not creds:
        raise PermissionError(
            "YouTube account is not connected yet! Please click 'Connect YouTube' to authorize your channel."
        )
    return build('youtube', 'v3', credentials=creds)


def get_youtube_channel_info() -> Dict[str, Any]:
    """Returns connected channel details or connected: False."""
    try:
        creds = get_credentials(allow_interactive=False)
        if not creds or not creds.valid:
            return {"connected": False, "channel_title": None, "channel_id": None}
        youtube = build('youtube', 'v3', credentials=creds)
        res = youtube.channels().list(mine=True, part='snippet').execute()
        items = res.get('items', [])
        if items:
            snippet = items[0].get('snippet', {})
            return {
                "connected": True,
                "channel_title": snippet.get('title', 'My Channel'),
                "channel_id": items[0].get('id'),
                "custom_url": snippet.get('customUrl', '')
            }
        return {"connected": True, "channel_title": "Connected Channel", "channel_id": None}
    except Exception as e:
        return {"connected": False, "error": str(e)}


_auth_thread = None


def trigger_browser_auth():
    """Spawns non-blocking local server auth flow so browser opens for login."""
    global _auth_thread
    if _auth_thread and _auth_thread.is_alive():
        return {"status": "in_progress", "message": "Authentication already running in browser"}

    def run():
        try:
            get_credentials(allow_interactive=True)
            print("[YouTube Auth] Successfully authenticated and saved token.pickle!")
        except Exception as e:
            print(f"[YouTube Auth] Interactive auth error: {e}")

    _auth_thread = threading.Thread(target=run, daemon=True)
    _auth_thread.start()
    return {"status": "started", "message": "Browser opened for Google account authorization"}


def build_youtube_metadata(
    song_title: str,
    artist_name: str,
    lyrics_data: Optional[list] = None,
    theme: str = "",
    aspect_ratio: str = "16:9",
    custom_title: Optional[str] = None,
    custom_desc: Optional[str] = None,
    custom_tags: Optional[list] = None
) -> Dict[str, Any]:
    """Generates viral, perfectly formatted YouTube title, rich description with lyrics and timestamps, and SEO tags."""
    import re

    clean_title = (song_title or "VIDA Official Track").strip()
    clean_artist = (artist_name or "").strip()
    if clean_artist.lower() in ("official audio", "vida project", "unknown", "none"):
        clean_artist = ""

    # Detect Khmer script
    is_khmer = any('\u1780' <= c <= '\u17FF' for c in (clean_title + " " + clean_artist))

    # 1. Perfectly Formatted YouTube Title (Max 100 characters)
    if custom_title and custom_title.strip():
        final_title = custom_title.strip()[:100]
    else:
        if is_khmer:
            tagline = " | ចម្រៀងកាយវិការ [Official 4K 60FPS Video]"
            alt_tagline = " [Official Lyrics Video]"
        else:
            tagline = " | Official Audio Visualizer (60 FPS)"
            alt_tagline = " [Official Video]"

        if clean_artist:
            lead = f"{clean_artist} - {clean_title}"
        else:
            lead = clean_title

        if len(lead + tagline) <= 100:
            final_title = lead + tagline
        elif len(lead + alt_tagline) <= 100:
            final_title = lead + alt_tagline
        else:
            final_title = lead[:100]

    # 2. Rich, High-Converting YouTube Description
    if custom_desc and custom_desc.strip():
        final_desc = custom_desc.strip()[:5000]
    else:
        desc_lines = []
        if clean_artist:
            desc_lines.append(f"🎵 Song Title: {clean_title}")
            desc_lines.append(f"🎙️ Artist / Singer: {clean_artist}")
        else:
            desc_lines.append(f"🎵 Song Title: {clean_title}")

        theme_name = theme.replace("_", " ").title() if theme else "Fluid Wave"
        desc_lines.append(f"✨ Visualizer: {theme_name} (60 FPS Ultra-HD)")
        desc_lines.append(f"📐 Format: {'Vertical (9:16 Shorts/Reels)' if aspect_ratio == '9:16' else 'Cinematic (16:9 4K)'}")
        desc_lines.append("⚡ Visual Production: VIDA Studio — Visual Intelligent Dynamic Audio-Video")
        desc_lines.append("")
        desc_lines.append("═" * 40)

        # Include Timed Synchronized Lyrics if available
        if lyrics_data and len(lyrics_data) > 0:
            desc_lines.append("📝 FULL SYNCHRONIZED LYRICS / ទំនុកច្រៀង:")
            desc_lines.append("═" * 40)
            for item in lyrics_data:
                txt = item.get("text", "").strip() if isinstance(item, dict) else str(item).strip()
                s = float(item.get("start", 0)) if isinstance(item, dict) else 0.0
                if txt:
                    mm = int(s // 60)
                    ss = int(s % 60)
                    desc_lines.append(f"[{mm:02d}:{ss:02d}] {txt}")
            desc_lines.append("═" * 40)
            desc_lines.append("")

        # SEO Call to Action
        desc_lines.append("🔔 Don't forget to Like, Share, and Subscribe for more high-fidelity visualizer tracks!")
        desc_lines.append("")

        # SEO Hashtags
        hashtags = ["#VIDAStudio", "#AudioVisualizer", "#MusicVideo", "#60FPS", "#KaraokeLyrics"]
        if is_khmer:
            hashtags.extend(["#KhmerMusic", "#KhmerSong", "#ចម្រៀងខ្មែរ", "#ចម្រៀងថ្មីៗ"])
        if clean_artist:
            tag_artist = re.sub(r'[^\w\u1780-\u17FF]', '', clean_artist)
            if tag_artist:
                hashtags.append(f"#{tag_artist}")
        tag_title = re.sub(r'[^\w\u1780-\u17FF]', '', clean_title)
        if tag_title:
            hashtags.append(f"#{tag_title}")

        desc_lines.append(" ".join(hashtags[:12]))
        final_desc = "\n".join(desc_lines)[:5000]

    # 3. Tags (Max 25 tags)
    if custom_tags:
        final_tags = [str(t).strip() for t in custom_tags if str(t).strip()]
    else:
        final_tags = ["VIDA", "VIDA Studio", "Music Video", "Audio Visualizer", "60 FPS", "Karaoke", "Lyrics"]
        if clean_title:
            final_tags.append(clean_title)
        if clean_artist:
            final_tags.append(clean_artist)
            final_tags.append(f"{clean_artist} music")
        if is_khmer:
            final_tags.extend(["Khmer song", "Khmer music", "ចម្រៀងខ្មែរ", "ភ្លេងការ", "ចម្រៀងកាយវិការ", "ចម្រៀងថ្មី"])

    return {
        "title": final_title,
        "description": final_desc,
        "tags": final_tags[:25]
    }


def upload_video_to_youtube(
    video_path: str,
    title: str,
    description: str,
    tags: list,
    category_id: str = "10",
    privacy_status: str = "public",
    progress_callback=None
) -> str:
    """Uploads a video to YouTube with specified privacy status (public, unlisted, private)."""
    try:
        youtube = get_authenticated_service(allow_interactive=False)

        valid_privacy = privacy_status.lower() if privacy_status.lower() in ("public", "unlisted", "private") else "public"

        body = {
            'snippet': {
                'title': title[:100],
                'description': description[:5000],
                'tags': tags,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': valid_privacy,
                'selfDeclaredMadeForKids': False
            }
        }

        chunk_size = 10 * 1024 * 1024
        media = MediaFileUpload(video_path, chunksize=chunk_size, resumable=True)

        request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media
        )

        print(f"[YouTube Uploader] Starting upload for '{title}' (Privacy: {valid_privacy})...")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                print(f"[YouTube Uploader] Uploaded {progress}%")
                if progress_callback:
                    progress_callback(progress)

        video_id = response.get('id')
        video_url = f"https://youtu.be/{video_id}"
        print(f"[YouTube Uploader] Upload Complete! Video URL: {video_url}")
        return video_url
    except Exception as e:
        print(f"[YouTube Uploader] Error: {e}")
        raise e
