"""
Where VIDA keeps its files, and how an audio path sent by the studio is found on disk.

The studio sends audio paths in several shapes: absolute, relative to uploads/, URL-encoded,
or just a file name. Every endpoint resolves them here so they all agree on which file is meant.
"""

import os
import urllib.parse
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
AUDIO_DIR = os.path.join(UPLOAD_DIR, "audio")
LYRICS_DIR = os.path.join(UPLOAD_DIR, "lyrics")
VIDEO_DIR = os.path.join(UPLOAD_DIR, "video")
IMAGES_DIR = os.path.join(UPLOAD_DIR, "images")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

for _dir in (UPLOAD_DIR, AUDIO_DIR, LYRICS_DIR, VIDEO_DIR, IMAGES_DIR, OUTPUT_DIR, FRONTEND_DIR):
    os.makedirs(_dir, exist_ok=True)

AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".m4a", ".ogg")


def _candidates(path: str):
    rel = path.replace("\\", "/").lstrip("/")
    yield path
    yield os.path.abspath(path)
    yield os.path.join(AUDIO_DIR, os.path.basename(rel))
    yield os.path.join(UPLOAD_DIR, rel)


def find_audio_file(audio_path: Optional[str]) -> Optional[str]:
    """Absolute path of the file the studio means by `audio_path`, or None if it is not on disk."""
    if not audio_path:
        return None
    # Try the path as sent first: a real file name may itself contain '%'.
    decoded = urllib.parse.unquote(audio_path)
    for variant in dict.fromkeys((audio_path, decoded)):
        for candidate in _candidates(variant):
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
    return None


def latest_audio_file() -> Optional[str]:
    """The most recently modified track in uploads/audio, or None when there is none."""
    tracks = [
        os.path.join(AUDIO_DIR, name) for name in os.listdir(AUDIO_DIR)
        if name.lower().endswith(AUDIO_EXTENSIONS)
    ]
    return max(tracks, key=os.path.getmtime, default=None)


def find_audio_file_or_latest(audio_path: Optional[str]) -> Optional[str]:
    """
    Like find_audio_file, but falls back to the newest track. Only for saving/loading cue sheets,
    where the studio may not know the server path yet. Never use it for alignment: syncing lyrics
    to the wrong song is worse than an error.
    """
    return find_audio_file(audio_path) or latest_audio_file()
