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
