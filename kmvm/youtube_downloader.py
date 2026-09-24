"""
YouTube Audio Downloader for Khmer Music Video Maker
Downloads audio from YouTube links using yt-dlp.
Uses ffmpeg bundled with imageio-ffmpeg.
"""

import os
import re
import subprocess
import sys
from typing import Optional, Tuple


def _get_ffmpeg_dir() -> str:
    """Get the directory containing ffmpeg from imageio-ffmpeg and guarantee ffmpeg.exe exists."""
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_dir = os.path.dirname(ffmpeg_exe)
        ffmpeg_standard = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        if not os.path.exists(ffmpeg_standard) and os.path.exists(ffmpeg_exe):
            import shutil
            shutil.copy2(ffmpeg_exe, ffmpeg_standard)
        return ffmpeg_dir
    except Exception:
        # Fallback to venv/Scripts if ffmpeg.exe is there
        scripts_ffmpeg = os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe")
        if os.path.exists(scripts_ffmpeg):
            return os.path.dirname(sys.executable)
        return ""


def _get_yt_dlp_path() -> str:
    """Get path to yt-dlp executable."""
    yt_dlp_path = os.path.join(os.path.dirname(sys.executable), "yt-dlp.exe")
    if os.path.exists(yt_dlp_path):
        return yt_dlp_path
    return "yt-dlp"


def extract_youtube_url(text: str) -> Optional[str]:
    """Extract a YouTube URL from any surrounding text."""
    patterns = [
        r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+(?:[&?][\w=%-]*)*',
        r'https?://youtu\.be/[\w-]+(?:\?[\w=&%-]*)?',
        r'https?://(?:www\.)?youtube\.com/shorts/[\w-]+',
        r'https?://music\.youtube\.com/watch\?v=[\w-]+(?:[&?][\w=%-]*)*',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(0)
    return None


def is_youtube_url(text: str) -> bool:
    """Check if the given text contains a valid YouTube URL."""
    return extract_youtube_url(text) is not None


def _clean_url(url: str) -> str:
    """Extract pure YouTube URL and strip playlist parameters."""
    # First extract just the URL from any surrounding text
    extracted = extract_youtube_url(url)
    if extracted:
        url = extracted
    else:
        url = url.strip()
    # Remove &list=... and &start_radio=... parameters
    url = re.sub(r'[&?](list|start_radio|index|si)=[^&]*', '', url)
    # Clean up double && or trailing &
    url = re.sub(r'&&+', '&', url)
    url = re.sub(r'\?&', '?', url)
    url = url.rstrip('&?')
    return url


def download_youtube_audio(url: str, output_dir: str, on_progress=None) -> Tuple[Optional[str], Optional[dict]]:
    """
    Download audio from a YouTube URL as high-quality audio.

    Args:
        url: YouTube video URL
        output_dir: Directory to save the audio file
        on_progress: Optional callback(status_text: str)

    Returns:
        Tuple of (output_file_path, info_dict) or (None, None) on failure
    """
    os.makedirs(output_dir, exist_ok=True)

    yt_dlp_path = _get_yt_dlp_path()
    ffmpeg_dir = _get_ffmpeg_dir()
    clean_url = _clean_url(url)

    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    def notify_progress(pct: int, msg: str):
        if on_progress:
            try:
                import inspect
                sig = inspect.signature(on_progress)
                if len(sig.parameters) >= 2:
                    on_progress(pct, msg)
                else:
                    on_progress(f"{msg} ({pct}%)")
            except Exception:
                try:
                    on_progress(pct, msg)
                except Exception:
                    pass

    notify_progress(5, "Connecting to YouTube...")

    # Build base args with ffmpeg location
    base_args = [yt_dlp_path]
    if ffmpeg_dir:
        base_args.extend(["--ffmpeg-location", ffmpeg_dir])

    # Get video info first (title, duration, artist)
    info = None
    try:
        info_cmd = base_args + [
            "--print", "%(title)s|||%(duration)s|||%(uploader)s",
            "--no-download",
            "--no-playlist",
            "--no-warnings",
            clean_url
        ]
        result = subprocess.run(
            info_cmd,
            capture_output=True, text=True, timeout=60, encoding="utf-8"
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|||")
            if len(parts) >= 3:
                dur_str = parts[1].strip()
                try:
                    duration = float(dur_str)
                except (ValueError, TypeError):
                    duration = 0
                info = {
                    "title": parts[0].strip(),
                    "duration": duration,
                    "artist": parts[2].strip(),
                }
                notify_progress(15, f"Found: {info['title'][:40]}")
    except subprocess.TimeoutExpired:
        print("[KMVM] YouTube info timed out, continuing with download...", flush=True)
        notify_progress(15, "Downloading audio...")
    except Exception as e:
        print(f"[KMVM] YouTube info error: {e}", flush=True)
        notify_progress(15, "Downloading audio...")

    # Download audio — try multiple formats for best compatibility
    formats_to_try = [
        # Try 1: Best audio with Khmer & English subtitles
        {
            "args": [
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "0",
            ],
            "no_subs": False,
            "label": "MP3"
        },
        # Try 2: Best audio, keep original format
        {
            "args": [
                "-f", "bestaudio",
                "--no-post-overwrites",
            ],
            "no_subs": False,
            "label": "best audio (original)"
        },
        # Try 3: Direct audio without subtitles (bypasses any YouTube 429 subtitle blocks)
        {
            "args": [
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "0",
            ],
            "no_subs": True,
            "label": "MP3 (direct audio without subtitles)"
        }
    ]

    for fmt in formats_to_try:
        try:
            sub_args = []
            if not fmt.get("no_subs", False):
                sub_args = [
                    "--write-subs",
                    "--write-auto-subs",
                    "--sub-langs", "km,km-orig,en,en-orig",
                    "--sub-format", "vtt/srt/best",
                ]

            cmd = base_args + fmt["args"] + [
                "-i",  # Ignore subtitle errors (like HTTP 429) so audio still downloads
                "--no-mtime",
                "--newline",
                "--print", "after_move:filepath",
            ] + sub_args + [
                "-o", output_template,
                "--no-playlist",
                "--no-warnings",
                "--no-check-certificates",
                clean_url
            ]

            notify_progress(20, f"Downloading stream ({fmt['label']})...")
            print(f"[KMVM] Running: {' '.join(cmd)}", flush=True)

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace"
            )

            stdout_lines = []
            for line in process.stdout:
                line_str = line.strip()
                if not line_str:
                    continue
                stdout_lines.append(line_str)

                # Real-time percentage parser: [download]  45.2% of ...
                m = re.search(r'\[download\]\s+([\d\.]+)%', line_str)
                if m:
                    try:
                        raw_pct = float(m.group(1))
                        calc_pct = int(20 + raw_pct * 0.65)
                        notify_progress(calc_pct, f"Downloading audio ({raw_pct:.0f}%)...")
                    except ValueError:
                        pass
                elif "ExtractAudio" in line_str or "Destination" in line_str:
                    notify_progress(88, "Extracting high-quality MP3...")
                elif "[info] Writing video subtitles" in line_str:
                    notify_progress(94, "Syncing subtitles...")

            process.wait(timeout=180)

            # Check if audio was created (even if yt-dlp threw a subtitle 429 warning)
            if stdout_lines:
                for line in reversed(stdout_lines):
                    candidate = line.strip()
                    if candidate and os.path.exists(candidate):
                        ext = os.path.splitext(candidate)[1].lower()
                        if ext in {".mp3", ".wav", ".m4a", ".opus", ".webm", ".ogg", ".aac", ".flac"}:
                            audio_file = convert_to_mp3(candidate)
                            notify_progress(100, "Download complete!")
                            print(f"[KMVM] Downloaded (via yt-dlp output): {audio_file}", flush=True)
                            return audio_file, info

            title_hint = info.get("title") if info else None
            audio_file = _find_latest_audio_file(output_dir, title_hint=title_hint)
            if audio_file:
                notify_progress(100, "Download complete!")
                print(f"[KMVM] Downloaded (via directory scan): {audio_file}", flush=True)
                return audio_file, info

            print(f"[KMVM] yt-dlp ({fmt['label']}) stderr/output: {' '.join(stdout_lines[-5:])[:300]}", flush=True)

        except subprocess.TimeoutExpired:
            print(f"[KMVM] Download timed out for format {fmt['label']}", flush=True)
            notify_progress(20, "Download timed out, trying next format...")
        except Exception as e:
            print(f"[KMVM] Download error ({fmt['label']}): {e}", flush=True)

    notify_progress(0, "Download failed!")
    return None, None


def convert_to_mp3(src_path: str) -> str:
    """Converts webm/opus/m4a to standard MP3 for 100% reliable desktop playback."""
    if src_path.lower().endswith(".mp3"):
        return src_path
    mp3_path = os.path.splitext(src_path)[0] + ".mp3"
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [ffmpeg_exe, "-y", "-i", src_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", mp3_path]
        res = subprocess.run(cmd, capture_output=True, timeout=60)
        if res.returncode == 0 and os.path.exists(mp3_path):
            print(f"[KMVM Audio] ✓ Converted to MP3: {os.path.basename(mp3_path)}", flush=True)
            return mp3_path
    except Exception as e:
        print(f"[KMVM Audio] MP3 conversion note: {e}", flush=True)
    return src_path


def _find_latest_audio_file(directory: str, title_hint: Optional[str] = None) -> Optional[str]:
    """Find the most recently modified audio file in the directory, prioritizing title match and ignoring test/demo files."""
    audio_extensions = {".mp3", ".wav", ".m4a", ".opus", ".webm", ".ogg", ".aac", ".flac", ".mp4"}

    # Priority 1: Match by title hint if available
    if title_hint:
        sanitized = re.sub(r'[\\/*?:"<>|]', '', title_hint).strip().lower()
        candidates = []
        for f in os.listdir(directory):
            name, ext = os.path.splitext(f)
            if ext.lower() in audio_extensions:
                clean_name = re.sub(r'[\\/*?:"<>|]', '', name).strip().lower()
                if sanitized and (sanitized in clean_name or clean_name in sanitized):
                    candidates.append(os.path.join(directory, f))
        if candidates:
            candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return convert_to_mp3(candidates[0])

    # Priority 2: Fallback to newest audio file, strictly excluding test/demo files
    best_file = None
    best_time = 0

    for f in os.listdir(directory):
        f_lower = f.lower()
        # Strictly ignore test and demo files
        if f_lower.startswith(("test_", "demo_")):
            continue

        ext = os.path.splitext(f)[1].lower()
        if ext in audio_extensions:
            full_path = os.path.join(directory, f)
            try:
                mtime = os.path.getmtime(full_path)
                if mtime > best_time:
                    best_time = mtime
                    best_file = full_path
            except OSError:
                pass

    if best_file:
        best_file = convert_to_mp3(best_file)

    return best_file
