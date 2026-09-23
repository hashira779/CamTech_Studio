"""
Stage 1 — Audio Conversion
Converts any input audio/video file to a 16 kHz mono WAV that both
Demucs and faster-whisper can consume directly.

Uses the FFmpeg binary bundled with imageio-ffmpeg (already in VIDA venv)
so no system FFmpeg installation is required.
"""

import os
import subprocess
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def get_ffmpeg_path() -> str:
    """Return the path to the FFmpeg binary from imageio-ffmpeg or system PATH."""
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        path = get_ffmpeg_exe()
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass

    # Fallback: try system ffmpeg
    import shutil
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg

    raise FileNotFoundError(
        "FFmpeg not found. Install imageio-ffmpeg or add ffmpeg to PATH."
    )


def convert_to_wav(
    input_path: str,
    output_path: str,
    sample_rate: int = 16000,
    channels: int = 1,
) -> str:
    """
    Convert any audio/video file to a 16 kHz mono WAV.

    Args:
        input_path:  Path to source audio/video (mp3, mp4, m4a, flac, wav, …)
        output_path: Destination .wav path
        sample_rate: Target sample rate in Hz (default 16000 for Whisper)
        channels:    Number of channels (default 1 = mono)

    Returns:
        output_path on success.

    Raises:
        FileNotFoundError: if input_path does not exist.
        RuntimeError: if FFmpeg conversion fails.
    """
    input_path = str(input_path)
    output_path = str(output_path)

    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    ffmpeg = get_ffmpeg_path()

    cmd = [
        ffmpeg,
        "-y",                          # overwrite without prompting
        "-i", input_path,
        "-vn",                         # no video
        "-acodec", "pcm_s16le",        # 16-bit PCM
        "-ar", str(sample_rate),       # target sample rate
        "-ac", str(channels),          # mono
        "-hide_banner",
        "-loglevel", "error",
        output_path,
    ]

    log.info(f"[stage1] Converting: {input_path} → {output_path}")
    log.debug(f"[stage1] FFmpeg cmd: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    if not os.path.isfile(output_path):
        raise RuntimeError(f"FFmpeg ran successfully but output file is missing: {output_path}")

    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    log.info(f"[stage1] Done. Output: {output_path} ({file_size_mb:.1f} MB)")

    return output_path


def probe_duration(input_path: str) -> float:
    """
    Returns the duration of an audio/video file in seconds using FFprobe.
    Returns 0.0 if probe fails.
    """
    try:
        ffmpeg = get_ffmpeg_path()
        ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
        if not os.path.isfile(ffprobe):
            # Try stripping .exe and re-adding ffprobe
            ffprobe = os.path.join(os.path.dirname(ffmpeg), "ffprobe")
            if os.name == "nt":
                ffprobe += ".exe"

        if not os.path.isfile(ffprobe):
            return 0.0

        cmd = [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0
