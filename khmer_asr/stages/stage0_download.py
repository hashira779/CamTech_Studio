"""
Stage 0 — YouTube Download
Downloads audio from a YouTube URL using yt-dlp and saves it as MP3
(or best audio format) ready for the rest of the pipeline.

Uses the yt-dlp binary already installed in the VIDA venv.
No API key required. Respects --no-playlist to avoid downloading entire playlists.
"""

import os
import sys
import subprocess
import logging
import json
import re
from pathlib import Path

log = logging.getLogger(__name__)


def is_youtube_url(text: str) -> bool:
    """Returns True if the input looks like a YouTube URL."""
    patterns = [
        r"youtube\.com/watch",
        r"youtu\.be/",
        r"youtube\.com/shorts/",
        r"youtube\.com/live/",
        r"music\.youtube\.com/",
    ]
    return any(re.search(p, text) for p in patterns)


def get_ytdlp_path() -> str:
    """Return the path to yt-dlp binary from venv or system PATH."""
    # Check VIDA venv Scripts directory first
    here = os.path.dirname(os.path.abspath(__file__))
    venv_root = os.path.join(here, "..", "..", "venv", "Scripts")
    candidates = [
        os.path.join(venv_root, "yt-dlp.exe"),
        os.path.join(venv_root, "yt-dlp"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)

    # Fallback to system PATH
    import shutil
    sys_ytdlp = shutil.which("yt-dlp")
    if sys_ytdlp:
        return sys_ytdlp

    raise FileNotFoundError(
        "yt-dlp not found.\n"
        "Install: pip install yt-dlp"
    )


def get_ffmpeg_path() -> str:
    """Return bundled FFmpeg path for yt-dlp --ffmpeg-location."""
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        path = get_ffmpeg_exe()
        if path and os.path.isfile(path):
            return os.path.dirname(path)  # yt-dlp wants the directory
    except Exception:
        pass
    return ""


def get_video_info(url: str) -> dict:
    """
    Fetch video metadata (title, duration, uploader) without downloading.
    Returns a dict with keys: title, duration, uploader, upload_date, thumbnail.
    """
    ytdlp = get_ytdlp_path()
    cmd = [
        ytdlp,
        "--no-warnings",
        "--no-check-certificates",
        "--print", "%(title)s|||%(duration)s|||%(uploader)s|||%(upload_date)s",
        "--no-playlist",
        url,
    ]

    ffmpeg_dir = get_ffmpeg_path()
    if ffmpeg_dir:
        cmd += ["--ffmpeg-location", ffmpeg_dir]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("|||")
            if len(parts) >= 3:
                return {
                    "title": parts[0],
                    "duration": int(parts[1]) if parts[1].isdigit() else 0,
                    "uploader": parts[2],
                    "upload_date": parts[3] if len(parts) > 3 else "",
                }
    except Exception:
        pass

    return {"title": "unknown", "duration": 0, "uploader": "", "upload_date": ""}


def download_audio(
    url: str,
    output_dir: str,
    audio_format: str = "mp3",
    audio_quality: str = "0",
    keep_video: bool = False,
) -> str:
    """
    Download audio from a YouTube URL using yt-dlp.

    Args:
        url:           YouTube URL (watch, shorts, music, etc.)
        output_dir:    Directory to save the downloaded file
        audio_format:  Output format: "mp3", "m4a", "wav", "best"
        audio_quality: yt-dlp audio quality: "0" = best, "9" = worst
        keep_video:    If True, download full video (larger, slower)

    Returns:
        Path to the downloaded audio file.

    Raises:
        RuntimeError: if yt-dlp fails.
        FileNotFoundError: if yt-dlp binary not found.
    """
    ytdlp = get_ytdlp_path()
    os.makedirs(output_dir, exist_ok=True)

    log.info(f"[stage0] Fetching video info: {url}")
    info = get_video_info(url)
    duration_min = info["duration"] // 60
    log.info(f"[stage0] Title:    {info['title']}")
    log.info(f"[stage0] Uploader: {info['uploader']}")
    log.info(f"[stage0] Duration: {info['duration']}s ({duration_min} min)")

    # Output template — sanitise filename
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    cmd = [
        ytdlp,
        "--no-warnings",
        "--no-check-certificates",
        "--no-playlist",          # never download full playlist
        "--ignore-errors",
        "--print", "after_move:filepath",  # print final file path
        "--no-mtime",
    ]

    ffmpeg_dir = get_ffmpeg_path()
    if ffmpeg_dir:
        cmd += ["--ffmpeg-location", ffmpeg_dir]

    if audio_format == "best" or keep_video:
        # Download best audio stream, no conversion
        cmd += ["-f", "bestaudio"]
    else:
        # Extract audio and convert to mp3/m4a/wav
        cmd += [
            "-x",
            "--audio-format", audio_format,
            "--audio-quality", audio_quality,
        ]

    cmd += [
        "-o", output_template,
        url,
    ]

    log.info(f"[stage0] Downloading audio ({audio_format})...")
    log.debug(f"[stage0] yt-dlp cmd: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Extract the final file path from stdout (printed by --print after_move:filepath)
    downloaded_path = None
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line and os.path.isfile(line):
            downloaded_path = line
            break

    if result.returncode != 0 and not downloaded_path:
        # Try to find the file by listing the directory
        for f in os.listdir(output_dir):
            if f.lower().endswith(f".{audio_format}") or f.lower().endswith(".webm") or f.lower().endswith(".m4a"):
                candidate = os.path.join(output_dir, f)
                if os.path.isfile(candidate):
                    downloaded_path = candidate
                    break

    if not downloaded_path:
        raise RuntimeError(
            f"yt-dlp failed (exit {result.returncode}).\n"
            f"stderr: {result.stderr[:500]}"
        )

    file_size_mb = os.path.getsize(downloaded_path) / (1024 * 1024)
    log.info(f"[stage0] Downloaded: {downloaded_path} ({file_size_mb:.1f} MB)")

    return downloaded_path
