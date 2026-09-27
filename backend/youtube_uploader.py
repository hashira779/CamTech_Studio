import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def get_authenticated_service():
    creds = None
    token_path = os.path.join(os.path.dirname(__file__), 'token.pickle')
    client_secret_path = os.path.join(os.path.dirname(__file__), 'client_secret.json')

    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)
            
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(client_secret_path):
                raise FileNotFoundError("client_secret.json is missing! Please place it in the backend folder.")
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)

    return build('youtube', 'v3', credentials=creds)

def upload_video_to_youtube(video_path, title, description, tags, category_id="10", progress_callback=None):
    try:
        youtube = get_authenticated_service()

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': 'private', # Private by default for safety
                'selfDeclaredMadeForKids': False
            }
        }

        # 10MB chunksize enables live progress reporting and resumable transmission
        chunk_size = 10 * 1024 * 1024
        media = MediaFileUpload(video_path, chunksize=chunk_size, resumable=True)

        request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media
        )

        print(f"[YouTube Uploader] Starting upload for {title}...")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                print(f"[YouTube Uploader] Uploaded {progress}%")
                if progress_callback:
                    progress_callback(progress)

        video_url = f"https://youtu.be/{response['id']}"
        print(f"[YouTube Uploader] Upload Complete! Video URL: {video_url}")
        return video_url
    except Exception as e:
        print(f"[YouTube Uploader] Error: {e}")
        raise e
