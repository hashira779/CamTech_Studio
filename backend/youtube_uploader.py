import os
import json
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
DEFAULTS_JSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'youtube_defaults.json')


def load_youtube_defaults() -> Dict[str, Any]:
    """Loads standard YouTube default metadata settings from backend/data/youtube_defaults.json."""
    if os.path.exists(DEFAULTS_JSON_PATH):
        try:
            with open(DEFAULTS_JSON_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[YouTube Defaults JSON] Warning: {e}")

    # Fallback structure
    return {
        "brand": {
            "channel_name": "VibeTunes",
            "tagline": "Visual Intelligent Dynamic Audio-Video",
            "studio_name": "VIDA Studio"
        },
        "title_templates": {
            "khmer": "{artist} - {title} | ចម្រៀងកាយវិការ [Official 4K 60FPS Video]",
            "international": "{artist} - {title} | Official Audio Visualizer (60 FPS)",
            "no_artist_khmer": "{title} | ចម្រៀងកាយវិការ [Official 4K 60FPS Video]",
            "no_artist_international": "{title} | Official Audio Visualizer (60 FPS)"
        },
        "description_template": {
            "header_lines": [
                "🎵 Song Title: {title}",
                "🎙️ Artist / Singer: {artist}",
                "✨ Visualizer: {theme} (60 FPS Ultra-HD)",
                "📐 Format: {format}",
                "⚡ Visual Production: {studio_name} — {tagline}"
            ],
            "lyrics_section": {
                "include_lyrics": True,
                "include_timestamps": True,
                "khmer_header": "📝 FULL SYNCHRONIZED LYRICS / ទំនុកច្រៀង:",
                "default_header": "📝 FULL SYNCHRONIZED LYRICS:"
            },
            "call_to_action": [
                "🔔 Don't forget to Like, Share, and Subscribe to {channel_name} for more high-fidelity visualizer tracks!"
            ]
        },
        "default_hashtags": [
            "#VibeTunes",
            "#VibeTunesMusic",
            "#AudioVisualizer",
            "#MusicVideo",
            "#60FPS",
            "#KaraokeLyrics"
        ],
        "language_hashtags": {
            "khmer": ["#KhmerMusic", "#KhmerSong", "#ចម្រៀងខ្មែរ", "#ចម្រៀងថ្មីៗ"],
            "vietnamese": ["#NhacViet", "#Vpop", "#NhacTre", "#LyricsVideo"],
            "international": ["#NewMusic", "#TopHits", "#ViralSong"]
        },
        "default_tags": [
            "VibeTunes",
            "VibeTunes Music",
            "VIDA Studio",
            "Music Video",
            "Audio Visualizer",
            "60 FPS",
            "Karaoke",
            "Lyrics"
        ]
    }


def save_youtube_defaults(data: Dict[str, Any]) -> bool:
    """Saves updated YouTube default metadata settings into backend/data/youtube_defaults.json."""
    try:
        os.makedirs(os.path.dirname(DEFAULTS_JSON_PATH), exist_ok=True)
        with open(DEFAULTS_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[YouTube Defaults JSON] Error saving: {e}")
        return False


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
        err_str = str(e)
        needs_enable = (
            "has not been used in project" in err_str or
            "it is disabled" in err_str or
            "accessNotConfigured" in err_str or
            "SERVICE_DISABLED" in err_str
        )
        return {
            "connected": False,
            "error": err_str,
            "needs_api_enable": needs_enable,
            "enable_url": "https://console.developers.google.com/apis/api/youtube.googleapis.com/overview?project=486767077998"
        }


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
    """Generates viral, perfectly formatted YouTube title, rich description with lyrics and timestamps, and SEO tags from JSON template."""
    import re

    cfg = load_youtube_defaults()
    brand_cfg = cfg.get("brand", {})
    channel_name = brand_cfg.get("channel_name", "VibeTunes")
    studio_name = brand_cfg.get("studio_name", "VIDA Studio")
    tagline = brand_cfg.get("tagline", "Visual Intelligent Dynamic Audio-Video")
    title_tpls = cfg.get("title_templates", {})
    desc_cfg = cfg.get("description_template", {})
    lyrics_cfg = desc_cfg.get("lyrics_section", {})

    clean_title = (song_title or "VIDA Official Track").strip()
    clean_artist = (artist_name or "").strip()
    if clean_artist.lower() in ("official audio", "vida project", "unknown", "none"):
        clean_artist = ""

    # Detect Khmer script
    is_khmer = any('\u1780' <= c <= '\u17FF' for c in (clean_title + " " + clean_artist))
    is_vietnamese = any(c in "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ" for c in (clean_title + " " + clean_artist))

    # 1. Perfectly Formatted YouTube Title (Max 100 characters from JSON template)
    if custom_title and custom_title.strip():
        final_title = custom_title.strip()[:100]
    else:
        if is_khmer:
            tpl = title_tpls.get("khmer", "{artist} - {title} | ចម្រៀងកាយវិការ [Official 4K 60FPS Video]") if clean_artist else title_tpls.get("no_artist_khmer", "{title} | ចម្រៀងកាយវិការ [Official 4K 60FPS Video]")
        else:
            tpl = title_tpls.get("international", "{artist} - {title} | Official Audio Visualizer (60 FPS)") if clean_artist else title_tpls.get("no_artist_international", "{title} | Official Audio Visualizer (60 FPS)")
        
        cand = tpl.format(artist=clean_artist, title=clean_title, channel_name=channel_name)
        final_title = cand[:100]

    # 2. Rich, High-Converting YouTube Description from JSON template
    if custom_desc and custom_desc.strip():
        final_desc = custom_desc.strip()[:5000]
    else:
        desc_lines = []
        theme_name = theme.replace("_", " ").title() if theme else "Fluid Wave"
        fmt_name = 'Vertical (9:16 Shorts/Reels)' if aspect_ratio == '9:16' else 'Cinematic (16:9 4K)'
        
        header_lines = desc_cfg.get("header_lines", [])
        for hl in header_lines:
            if "{artist}" in hl and not clean_artist:
                continue
            desc_lines.append(hl.format(
                title=clean_title,
                artist=clean_artist,
                theme=theme_name,
                format=fmt_name,
                studio_name=studio_name,
                tagline=tagline,
                channel_name=channel_name
            ))
        desc_lines.append("")
        desc_lines.append("═" * 40)

        # Include Timed Synchronized Lyrics if available
        if lyrics_cfg.get("include_lyrics", True) and lyrics_data and len(lyrics_data) > 0:
            header_txt = lyrics_cfg.get("khmer_header", "📝 FULL SYNCHRONIZED LYRICS / ទំនុកច្រៀង:") if is_khmer else lyrics_cfg.get("default_header", "📝 FULL SYNCHRONIZED LYRICS:")
            desc_lines.append(header_txt)
            desc_lines.append("═" * 40)
            for item in lyrics_data:
                txt = item.get("text", "").strip() if isinstance(item, dict) else str(item).strip()
                s = float(item.get("start", 0)) if isinstance(item, dict) else 0.0
                if txt:
                    if lyrics_cfg.get("include_timestamps", True):
                        mm = int(s // 60)
                        ss = int(s % 60)
                        desc_lines.append(f"[{mm:02d}:{ss:02d}] {txt}")
                    else:
                        desc_lines.append(txt)
            desc_lines.append("═" * 40)
            desc_lines.append("")

        for cta in desc_cfg.get("call_to_action", []):
            desc_lines.append(cta.format(channel_name=channel_name))
        desc_lines.append("")

        # SEO Hashtags from JSON
        lang_hashtags = cfg.get("language_hashtags", {})
        hashtags = list(cfg.get("default_hashtags", ["#VibeTunes", "#AudioVisualizer", "#MusicVideo", "#60FPS"]))
        if is_khmer:
            hashtags.extend(lang_hashtags.get("khmer", ["#KhmerMusic", "#KhmerSong", "#ចម្រៀងខ្មែរ", "#ចម្រៀងថ្មីៗ"]))
        elif is_vietnamese:
            hashtags.extend(lang_hashtags.get("vietnamese", ["#NhacViet", "#Vpop", "#NhacTre", "#LyricsVideo"]))
        else:
            hashtags.extend(lang_hashtags.get("international", ["#NewMusic", "#TopHits", "#ViralSong"]))

        if clean_artist:
            tag_artist = re.sub(r'[^\w\u1780-\u17FF]', '', clean_artist)
            if tag_artist:
                hashtags.append(f"#{tag_artist}")
        tag_title = re.sub(r'[^\w\u1780-\u17FF]', '', clean_title)
        if tag_title:
            hashtags.append(f"#{tag_title}")

        desc_lines.append(" ".join(hashtags[:15]))
        final_desc = "\n".join(desc_lines)[:5000]

    # 3. Tags from JSON (Max 25 tags for YouTube Algorithm)
    if custom_tags:
        final_tags = [str(t).strip() for t in custom_tags if str(t).strip()]
    else:
        final_tags = list(cfg.get("default_tags", ["VibeTunes", "VibeTunes Music", "VIDA Studio", "Music Video", "Audio Visualizer", "60 FPS", "Karaoke", "Lyrics"]))
        if clean_title and clean_title not in final_tags:
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
