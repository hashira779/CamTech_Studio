"""
FastAPI Server for VIDA
Provides REST APIs for file uploads, Whisper AI speech-to-text auto-lyrics,
LRC subtitle parsing, asynchronous video rendering jobs, and studio UI serving.
"""

import time as _time
_app_boot_start = _time.time()
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
# Suppress CuPy CUDA warning (CuPy auto-detects CUDA at render time)
import warnings
warnings.filterwarnings("ignore", message="CUDA path could not be detected")
hf_cache_root = os.path.expanduser("~/.cache/huggingface/hub")
if os.path.exists(hf_cache_root):
    try:
        if any(d.startswith("models--") for d in os.listdir(hf_cache_root)):
            os.environ["HF_HUB_OFFLINE"] = "1"
    except Exception:
        pass
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
import re
import subprocess
import time
import uuid
import threading
import urllib.parse
import numpy as np
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from backend.lyric_engine import (
    WhisperTranscriber,
    parse_lrc_file,
    parse_subtitle_content,
    parse_subtitle_file,
    find_matching_subtitles,
    fetch_synced_lyrics_lrclib,
    detect_text_language,
    double_check_lyrics,
    export_lyrics_to_lrc,
    export_subtitles_content,
    export_subtitles_to_srt,
    export_subtitles_to_vtt,
    export_subtitles_to_lrc,
    export_subtitles_to_ass,
    export_subtitles_to_txt,
    format_srt_for_capcut,
    is_khmer_text,
    is_thai_text,
    tokenize_line_words,
    compute_weighted_word_timestamps
)
from backend.vocal_align import force_align_lyrics_to_audio
from kmvm.youtube_downloader import download_youtube_audio, is_youtube_url, extract_youtube_url
from backend.llm_engine import llm_engine

# Lazy imports for heavy modules (saves ~1.5s startup: cv2, PIL, cupy init)
_VideoRenderer = None
_AISongUnderstandingEngine = None
_ThumbnailGenerator = None
_demo_audio = None

def _get_VideoRenderer():
    global _VideoRenderer
    if _VideoRenderer is None:
        from backend.renderer import VideoRenderer as _VR
        _VideoRenderer = _VR
    return _VideoRenderer

def _get_AISongUnderstandingEngine():
    global _AISongUnderstandingEngine
    if _AISongUnderstandingEngine is None:
        from kmvm.ai_engine import AISongUnderstandingEngine as _AI
        _AISongUnderstandingEngine = _AI
    return _AISongUnderstandingEngine

def _get_ThumbnailGenerator():
    global _ThumbnailGenerator
    if _ThumbnailGenerator is None:
        from kmvm.thumbnail_generator import ThumbnailGenerator as _TG
        _ThumbnailGenerator = _TG
    return _ThumbnailGenerator

def _get_demo_audio():
    global _demo_audio
    if _demo_audio is None:
        from backend import demo_audio as _da
        _demo_audio = _da
    return _demo_audio

# Directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
AUDIO_DIR = os.path.join(UPLOAD_DIR, "audio")
LYRICS_DIR = os.path.join(UPLOAD_DIR, "lyrics")
VIDEO_DIR = os.path.join(UPLOAD_DIR, "video")
IMAGES_DIR = os.path.join(UPLOAD_DIR, "images")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(LYRICS_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(FRONTEND_DIR, exist_ok=True)


def get_ffmpeg_binary() -> str:
    """Locate ffmpeg executable."""
    venv_ffmpeg = os.path.join(BASE_DIR, "venv", "Scripts", "ffmpeg.exe")
    if os.path.isfile(venv_ffmpeg):
        return venv_ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def extract_audio_from_video(video_path: str, audio_path: str) -> bool:
    """Extracts 44.1kHz stereo audio from video container into high-fidelity WAV."""
    try:
        ffmpeg_bin = get_ffmpeg_binary()
        cmd = [
            ffmpeg_bin, "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            audio_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        return res.returncode == 0 and os.path.isfile(audio_path) and os.path.getsize(audio_path) > 1000
    except Exception as e:
        print(f"[Upload] Audio extraction from video failed: {e}")
        return False


app = FastAPI(title="VIDA Video Studio API", version="1.0.0")

@app.on_event("startup")
async def _on_startup():
    elapsed = _time.time() - _app_boot_start
    msg = f"⚡ VIDA Studio ready in {elapsed:.1f}s"
    print(msg, flush=True)
    import logging; logging.getLogger("uvicorn").info(msg)

    # Started on an interpreter without the sync engines, the studio silently degrades to energy
    # spacing and looks broken. Say so on the console before the user has to guess.
    from backend.ctc_align import missing_dependency as aligner_missing
    from backend.vocal_separator import missing_dependency as separator_missing
    for label, gap in (("word aligner", aligner_missing()), ("vocal separator", separator_missing())):
        if gap:
            warn = (f"[VIDA] {label} disabled: '{gap}' is not installed for {sys.executable}. "
                    f"Start VIDA with run_vida_desktop.bat (venv\\Scripts\\python.exe).")
            print(warn, flush=True)
            logging.getLogger("uvicorn").warning(warn)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    """Guarantees CORS and audio streaming headers on every static file and API response."""
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    # Studio UI edits must show up on the next reload. Without this, browsers
    # heuristically cache JS/CSS modules and keep serving a stale interface.
    # no-cache still honours the ETag, so unchanged files stay cheap.
    path = request.url.path
    if path == "/" or path.startswith("/static") or path.startswith("/assets"):
        response.headers["Cache-Control"] = "no-cache"
    return response

@app.get("/health")
@app.get("/api/health")
def health_check():
    """Reports which sync engines this interpreter can actually run, without loading any model."""
    from backend.ctc_align import missing_dependency as aligner_missing
    from backend.vocal_separator import missing_dependency as separator_missing

    venv_python = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "venv", "Scripts", "python.exe")
    gap = aligner_missing()
    sep_gap = separator_missing()
    return {
        "status": "ok",
        "app": "VIDA Studio",
        "engine": "online",
        "python": sys.executable,
        "venv_python": venv_python if os.path.exists(venv_python) else None,
        "word_aligner": {"ready": gap is None, "missing": gap},
        "vocal_separator": {"ready": sep_gap is None, "missing": sep_gap},
        # The word aligner and Demucs each need a process of their own on this machine.
        "sync_grade": "word" if gap is None else ("phrase" if sep_gap is None else "energy"),
    }

_last_desktop_heartbeat = _time.time()
_desktop_client_connected = False

@app.post("/api/system/heartbeat")
def desktop_heartbeat():
    global _last_desktop_heartbeat, _desktop_client_connected
    _last_desktop_heartbeat = _time.time()
    _desktop_client_connected = True
    return {"status": "alive", "timestamp": _last_desktop_heartbeat}

@app.get("/api/system/heartbeat-status")
def desktop_heartbeat_status():
    global _last_desktop_heartbeat, _desktop_client_connected
    return {
        "client_connected": _desktop_client_connected,
        "seconds_since_heartbeat": _time.time() - _last_desktop_heartbeat
    }

@app.post("/api/system/shutdown")
def desktop_shutdown():
    """Safe endpoint: Allows multiple terminals, tabs, and windows to stay connected without disconnecting the server."""
    return {"status": "running", "message": "Multi-terminal persistence enabled; server remains active."}


# In-memory job tracker
jobs: Dict[str, Dict[str, Any]] = {}
transcriber_instance: Optional[WhisperTranscriber] = None

transcription_progress: Dict[str, Any] = {
    "status": "idle",
    "percent": 0,
    "stage": ""
}

def update_transcribe_progress(percent: int, stage: str):
    global transcription_progress
    transcription_progress = {
        "status": "in_progress" if percent < 100 else "complete",
        "percent": percent,
        "stage": stage
    }

youtube_progress: Dict[str, Any] = {
    "status": "idle",
    "percent": 0,
    "stage": ""
}

def update_youtube_progress(percent: int, stage: str):
    global youtube_progress
    youtube_progress = {
        "status": "in_progress" if percent < 100 else "complete",
        "percent": percent,
        "stage": stage,
        "timestamp": time.time()
    }

class RenderRequest(BaseModel):
    audio_path: str
    theme: str = "trap_circle"
    palette: str = "cyberpunk"
    aspect_ratio: str = "16:9"          # "16:9" or "9:16"
    fps: int = 60
    resolution: Optional[str] = "1080p" # "1080p", "720p", "480p"
    song_title: str = "VIDA Soundscape"
    artist_name: str = "Original Mix"
    title_scale: float = 1.5
    background_image: Optional[str] = None
    logo_image: Optional[str] = None
    center_text_primary: Optional[str] = "VIDA"
    center_text_secondary: Optional[str] = "FLUID WAVE"
    show_center_text: Optional[bool] = True
    lyrics_data: Optional[List[Dict[str, Any]]] = None
    lyric_style: str = "karaoke"
    # Second (translated) lyric track — display mode only, originals are never rewritten
    display_mode: str = "original_only"              # original_only | translation_only | bilingual
    translation_lines: Optional[List[str]] = None     # 1:1 with lyrics_data, same index order
    translation_lang: str = "en"
    translation_style: Optional[Dict[str, Any]] = None
    bar_count: int = 64
    bass_boost: float = 1.3
    auto_post_youtube: Optional[bool] = False
    youtube_privacy: Optional[str] = "public"
    youtube_title: Optional[str] = None
    youtube_description: Optional[str] = None
    youtube_tags: Optional[List[str]] = None

class TranscribeRequest(BaseModel):
    audio_path: str
    model_size: str = "base"
    language: Optional[str] = "auto"
    use_demucs: Optional[bool] = False
    force_ai: Optional[bool] = False
    song_title: Optional[str] = ""
    artist_name: Optional[str] = ""
    lyrics_data: Optional[List[Dict[str, Any]]] = None

class GenerateLyricsRequest(BaseModel):
    prompt: Optional[str] = ""
    genre: Optional[str] = "romantic"
    bpm: Optional[int] = 85

class PolishLyricsRequest(BaseModel):
    lyrics_text: str

class LrcParseRequest(BaseModel):
    lrc_text: str

class YouTubeRequest(BaseModel):
    url: str

class AnalyzeRequest(BaseModel):
    audio_path: str
    song_title: Optional[str] = ""
    artist_name: Optional[str] = ""

class ThumbnailRequest(BaseModel):
    song_title: str = "VIDA Track"
    artist_name: str = "Original Mix"
    background_image: Optional[str] = None

class LLMAnalyzeRequest(BaseModel):
    text: str
    lyrics_data: Optional[List[Dict[str, Any]]] = None

class LLMTranslateRequest(BaseModel):
    text: str

class LyricsVerifyRequest(BaseModel):
    lyrics_data: List[Dict[str, Any]]
    audio_path: Optional[str] = None

class LyricsCorrectReferenceRequest(BaseModel):
    lyrics_data: Optional[List[Dict[str, Any]]] = None
    reference_text: str
    audio_path: Optional[str] = None

class SubtitleExportRequest(BaseModel):
    lyrics_data: List[Dict[str, Any]]
    format: str = "srt"  # "srt", "vtt", "lrc", "ass", "txt"
    title: Optional[str] = "VIDA Studio Subtitles"
    artist: Optional[str] = ""

class SubtitleAIFixRequest(BaseModel):
    lyrics_data: List[Dict[str, Any]]
    audio_path: Optional[str] = None
    align_vocals: Optional[bool] = False

class GeminiKeyUpdateRequest(BaseModel):
    api_key: Optional[str] = ""

@app.get("/api/gemini/status")
def get_gemini_status():
    from backend.khmer_lyric_matcher import get_gemini_api_key, get_last_key_error
    key = get_gemini_api_key()
    configured = bool(key)
    masked = f"{key[:8]}...{key[-4:]}" if (key and len(key) > 12) else ("***" if key else "")
    last_err = get_last_key_error()
    return {
        "status": "success",
        "configured": configured,
        "masked_key": masked,
        "valid": last_err is None if configured else False,
        "last_error": last_err,
        "active_model": "gemini-3.8-flash"
    }

@app.post("/api/gemini/verify")
def verify_gemini_key_api(req: Optional[GeminiKeyUpdateRequest] = None):
    from backend.khmer_lyric_matcher import verify_gemini_api_key
    target_key = req.api_key.strip() if req and req.api_key else None
    valid, err_msg = verify_gemini_api_key(target_key)
    return {
        "status": "success" if valid else "error",
        "valid": valid,
        "error": err_msg
    }

@app.post("/api/gemini/update-key")
def update_gemini_key_api(req: GeminiKeyUpdateRequest):
    from backend.khmer_lyric_matcher import verify_gemini_api_key, set_gemini_api_key
    new_key = (req.api_key or "").strip()
    if not new_key:
        raise HTTPException(status_code=400, detail="Gemini API key cannot be empty")
    valid, err_msg = verify_gemini_api_key(new_key)
    if not valid:
        raise HTTPException(status_code=400, detail=f"API key verification failed: {err_msg}")
    saved = set_gemini_api_key(new_key)
    if not saved:
        raise HTTPException(status_code=500, detail="Failed to save API key to .env file")
    masked = f"{new_key[:8]}...{new_key[-4:]}" if len(new_key) > 12 else "***"
    return {
        "status": "success",
        "message": "Gemini API Key successfully verified and saved!",
        "masked_key": masked
    }

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Uploads audio, video, background image, or logo file to server with auto audio extraction."""
    ext = os.path.splitext(file.filename)[1].lower()
    unique_name = f"{uuid.uuid4().hex[:10]}{ext}"
    video_exts = [".mp4", ".webm", ".mov", ".mkv", ".avi", ".flv", ".wmv", ".m4v"]
    
    if ext in [".mp3", ".wav", ".m4a", ".ogg", ".flac"]:
        subfolder = "audio"
        target_dir = AUDIO_DIR
    elif ext in [".lrc", ".vtt", ".srt", ".txt"]:
        subfolder = "lyrics"
        target_dir = LYRICS_DIR
    elif ext in video_exts:
        subfolder = "video"
        target_dir = VIDEO_DIR
    elif ext in [".jpg", ".jpeg", ".png", ".webp"]:
        subfolder = "images"
        target_dir = IMAGES_DIR
    else:
        subfolder = ""
        target_dir = UPLOAD_DIR
        
    target_path = os.path.join(target_dir, unique_name)

    content = await file.read()
    with open(target_path, "wb") as f:
        f.write(content)

    url_path = f"/uploads/{subfolder}/{unique_name}" if subfolder else f"/uploads/{unique_name}"
    
    # If a video was uploaded, automatically extract clean audio track
    if ext in video_exts:
        audio_name = f"{os.path.splitext(unique_name)[0]}_audio.wav"
        extracted_audio_path = os.path.join(AUDIO_DIR, audio_name)
        extracted = extract_audio_from_video(target_path, extracted_audio_path)
        if extracted:
            print(f"[Upload] Successfully extracted clean audio from video {file.filename} -> {audio_name}")
            return {
                "filename": file.filename,
                "saved_path": extracted_audio_path,
                "audio_path": extracted_audio_path,
                "video_path": target_path,
                "url": f"/uploads/audio/{audio_name}",
                "video_url": url_path,
                "is_video": True
            }
        else:
            return {
                "filename": file.filename,
                "saved_path": target_path,
                "video_path": target_path,
                "url": url_path,
                "video_url": url_path,
                "is_video": True
            }

    return {
        "filename": file.filename,
        "saved_path": target_path,
        "audio_path": target_path if subfolder == "audio" else None,
        "url": url_path,
        "is_video": False
    }

@app.get("/api/library")
def get_local_library():
    """Returns a list of all audio and video files previously downloaded or uploaded."""
    files = []
    
    # Check Audio Directory
    if os.path.exists(AUDIO_DIR):
        for f in os.listdir(AUDIO_DIR):
            if f.lower().endswith(('.mp3', '.wav', '.flac', '.m4a', '.ogg')):
                # Hide raw temporary YouTube 11-char video IDs from library view
                if re.fullmatch(r'^[a-zA-Z0-9_-]{11}\.[a-zA-Z0-9]+$', f):
                    continue
                files.append({
                    "name": f,
                    "type": "audio",
                    "path": os.path.join(AUDIO_DIR, f).replace("\\", "/"),
                    "url": f"/uploads/audio/{urllib.parse.quote(f)}"
                })
                
    # Check Video Directory
    if os.path.exists(VIDEO_DIR):
        for f in os.listdir(VIDEO_DIR):
            if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                files.append({
                    "name": f,
                    "type": "video",
                    "path": os.path.join(VIDEO_DIR, f).replace("\\", "/"),
                    "url": f"/uploads/video/{urllib.parse.quote(f)}"
                })
                
    # Sort by modification time (newest first)
    try:
        files.sort(key=lambda x: os.path.getmtime(x["path"]), reverse=True)
    except Exception:
        files.sort(key=lambda x: x["name"])
        
    return {"status": "success", "files": files}

@app.get("/api/transcribe/progress")
def get_transcribe_progress():
    """Returns real-time progress percentage and current stage of AI transcription."""
    return transcription_progress

@app.post("/api/transcribe")
def transcribe_audio(req: TranscribeRequest):
    """Transcribes audio file to word-synced lyrics using local subtitles or Whisper AI."""
    global transcriber_instance

    if not os.path.exists(req.audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    target_lang = req.language
    if target_lang in ("auto", "", "None"):
        target_lang = None

    # Intelligent Khmer detection from audio path, title, and artist
    is_khmer_target = (
        target_lang == "km" or
        is_khmer_text(req.audio_path) or
        is_khmer_text(req.song_title or "") or
        is_khmer_text(req.artist_name or "")
    )
    if is_khmer_target and not target_lang:
        target_lang = "km"

    if req.lyrics_data and not req.force_ai:
        update_transcribe_progress(25, "Aligning original lyrics to the selected singer audio")
        audio_p = _resolve_alignment_audio(req.audio_path)
        verified, report, source = _align_selected_lyrics(req.lyrics_data, audio_p, progress_callback=update_transcribe_progress)
        _save_aligned_subtitles(verified, audio_p)
        update_transcribe_progress(100, f"Aligned {len(verified)} original lyric lines")
        return {
            "status": "success", "source": source,
            "detected_language": target_lang or detect_text_language(" ".join(line["text"] for line in verified)),
            "lyrics": verified, "count": len(verified), "report": report,
        }

    # 1. Ultra-Fast Check: Matching studio subtitle/LRC file (.km.lrc, .lrc, .srt, .vtt)
    # Disk cache is skipped when the user forces a re-sync, so the button always re-measures.
    sub_path = None
    if not req.force_ai:
        sub_path = find_matching_subtitles(req.audio_path, target_lang=target_lang)
        if sub_path and os.path.exists(sub_path):
            try:
                lyrics = parse_subtitle_file(sub_path, audio_path=req.audio_path)
                if lyrics and len(lyrics) >= 4:
                    sample_text = " ".join([l.get("text", "") for l in lyrics[:10]])
                    # Ensure we don't serve non-Khmer text for Khmer song
                    if not (is_khmer_target and not is_khmer_text(sample_text)):
                        update_transcribe_progress(100, f"✅ Verified lyrics ready ({len(lyrics)} lines)")
                        return {
                            "status": "success",
                            "source": "subtitle",
                            "file": os.path.basename(sub_path),
                            # Report the actual language of the caption, not a Khmer default.
                            "detected_language": target_lang or detect_text_language(sample_text),
                            "lyrics": lyrics,
                            "count": len(lyrics)
                        }
            except Exception as e:
                print(f"Subtitle parse warning: {e}")

    # Fast Online LRCLIB Check if not already found (only when not force_ai)
    if not sub_path and not req.force_ai:
        try:
            base_title = os.path.splitext(os.path.basename(req.audio_path))[0]
            clean_t, clean_a = clean_youtube_title_and_artist(req.song_title or base_title, req.artist_name or "")
            lrc_text = fetch_synced_lyrics_lrclib(clean_t, clean_a)
            if lrc_text:
                lrclib_lyrics = parse_subtitle_content(lrc_text)
                if lrclib_lyrics and len(lrclib_lyrics) >= 4:
                    base_audio = os.path.splitext(req.audio_path)[0]
                    lrc_dest = f"{base_audio}.lrc"
                    try:
                        with open(lrc_dest, "w", encoding="utf-8") as f:
                            f.write(lrc_text)
                    except Exception:
                        pass
                    update_transcribe_progress(100, "Loaded from online lyric library")
                    return {
                        "status": "success",
                        "source": "subtitle",
                        "file": os.path.basename(lrc_dest),
                        "detected_language": target_lang or detect_text_language(
                            " ".join(l.get("text", "") for l in lrclib_lyrics[:10])),
                        "lyrics": lrclib_lyrics,
                        "count": len(lrclib_lyrics)
                    }
        except Exception as lrc_err:
            print(f"[LRCLIB Fast-Path] Notice: {lrc_err}")

    # ⚡ LYRIC RETRIEVAL FAST-PATH — the cloud finds the authentic Khmer words; the timings are
    # always re-measured here against the singer audio, never trusted from the cloud.
    if is_khmer_target and (req.model_size == "gemini-fast" or req.model_size != "qwen3-khmer"):
        update_transcribe_progress(15, "Retrieving authentic Khmer lyrics...")
        try:
            try:
                from backend.khmer_lyric_matcher import match_or_fetch_khmer_lyrics
            except ImportError:
                from khmer_lyric_matcher import match_or_fetch_khmer_lyrics
            base_title = os.path.splitext(os.path.basename(req.audio_path))[0]
            clean_t, clean_a = clean_youtube_title_and_artist(base_title, use_gemini=True)
            matcher_res = match_or_fetch_khmer_lyrics(req.audio_path, clean_t, clean_a, progress_callback=update_transcribe_progress)
            if matcher_res:
                lrc_path, _matcher_aligned = matcher_res
                lyrics = parse_subtitle_file(lrc_path, audio_path=req.audio_path)
                if lyrics:
                    try:
                        audio_p = _resolve_alignment_audio(req.audio_path)
                        verified, report, local_source = _align_selected_lyrics(lyrics, audio_p)
                        update_transcribe_progress(100, f"Aligned {len(verified)} Khmer lines to the singer audio")
                        return {
                            "status": "success",
                            "source": local_source,
                            "file": os.path.basename(lrc_path),
                            "detected_language": target_lang or "km",
                            "lyrics": verified,
                            "count": len(verified),
                            "report": report,
                        }
                    except HTTPException as align_notice:
                        # Retrieval succeeded but the audio could not be re-measured; hand back
                        # the retrieved sheet and say plainly where its timings came from.
                        print(f"[Khmer Local Align] {align_notice.detail} — returning retrieved timings")
                        update_transcribe_progress(100, f"Retrieved {len(lyrics)} lines (timing not re-measured)")
                        return {
                            "status": "success",
                            "source": "retrieved-timing",
                            "file": os.path.basename(lrc_path),
                            "detected_language": target_lang or "km",
                            "lyrics": lyrics,
                            "count": len(lyrics),
                        }
        except Exception as gem_err:
            print(f"[Gemini Transcribe Fast-Path] Notice: {gem_err}. Continuing with fallback.")

    # 2. Vocal Separation (Demucs) if enabled or requested
    #    SKIP Demucs entirely when using Gemini Cloud AI — it doesn't need isolated vocals
    # 2. Vocal Separation (Demucs) — ONLY on CUDA GPU to prevent 4-minute CPU freeze!
    transcribe_path = req.audio_path
    can_run_demucs = False
    if req.use_demucs or req.model_size == "qwen3-khmer":
        try:
            try:
                from backend.vocal_separator import cuda_available
            except ImportError:
                from vocal_separator import cuda_available
            can_run_demucs = cuda_available()
            if not can_run_demucs:
                print("[Demucs] Skipped on CPU (no CUDA GPU). Using ultra-fast direct acoustic alignment.")
        except Exception:
            can_run_demucs = False

    if req.model_size != "gemini-fast" and can_run_demucs:
        try:
            try:
                from backend.vocal_separator import separate_vocals_demucs
            except ImportError:
                from vocal_separator import separate_vocals_demucs
            update_transcribe_progress(20, "Demucs: Isolating singing vocals from instruments...")
            sep_result = separate_vocals_demucs(req.audio_path, device="cuda", progress_callback=update_transcribe_progress)
            if sep_result.get("vocals") and os.path.exists(sep_result["vocals"]):
                transcribe_path = sep_result["vocals"]
                print(f"[Demucs] Using isolated vocals for transcription: {transcribe_path}")
        except Exception as demucs_err:
            print(f"[Demucs] Notice: {demucs_err}. Continuing with original audio.")

    # 3. Model transcription (Khmer Magic DB vs Qwen3-ASR vs Whisper)
    try:
        target_lang = req.language
        if target_lang in ("auto", "", "None"):
            target_lang = None

        # --- ALWAYS TRY MAGIC KHMER LYRIC MATCHER FIRST FOR KHMER SONGS ---
        if target_lang == "km" or is_khmer_text(req.audio_path) or is_khmer_text(req.song_title or ""):
            update_transcribe_progress(20, "Searching Verified Khmer Lyrics Database...")
            try:
                from backend.khmer_lyric_matcher import match_or_fetch_khmer_lyrics
                base_t = os.path.splitext(os.path.basename(req.audio_path))[0]
                c_title, c_artist = clean_youtube_title_and_artist(req.song_title or base_t, req.artist_name or "", use_gemini=False)
                
                gem_res = match_or_fetch_khmer_lyrics(req.audio_path, c_title, c_artist, progress_callback=update_transcribe_progress)
                if gem_res:
                    lrc_p, _ = gem_res
                    lyrics = parse_subtitle_file(lrc_p)
                    detected_lang = "km"
                    source_type = "magic-db-vad"
                    print(f"[KMVM Transcribe] ✅ Found {len(lyrics)} perfectly synced authentic lyrics in DB!")
                    
                    if lyrics and len(lyrics) > 0:
                        try:
                            base_audio, _ = os.path.splitext(req.audio_path)
                            lrc_dest = f"{base_audio}.km.lrc"
                            export_lyrics_to_lrc(lyrics, lrc_dest)
                        except: pass
                        
                        update_transcribe_progress(100, f"Lyrics successfully loaded from Magic DB!")
                        return {
                            "status": "success",
                            "source": source_type,
                            "detected_language": detected_lang,
                            "lyrics": lyrics,
                            "count": len(lyrics)
                        }
            except Exception as e:
                print(f"[KMVM Transcribe] Magic Khmer Fallback failed: {e}. Proceeding to ASR...")

        if req.model_size == "qwen3-khmer":
            update_transcribe_progress(40, "Preparing Qwen3-ASR 0.6B Khmer AI...")
            try:
                from backend.qwen_khmer_engine import QwenKhmerTranscriber
            except ImportError:
                from qwen_khmer_engine import QwenKhmerTranscriber
            qwen_instance = QwenKhmerTranscriber()
            lyrics = qwen_instance.transcribe(transcribe_path, progress_callback=update_transcribe_progress)
            detected_lang = "km"
            source_type = "qwen3-asr"
        else:
            # On CPU, use fast 'base' model (~5-10s) instead of 1.5GB large-v3-turbo (5 mins)!
            whisper_model = "base"
            if req.model_size and req.model_size not in ("gemini-fast", "qwen3-khmer", "auto", "default"):
                whisper_model = req.model_size

            update_transcribe_progress(5, f"Preparing Whisper ({whisper_model})...")
            if transcriber_instance is None or transcriber_instance.model_size != whisper_model:
                update_transcribe_progress(10, f"Loading Whisper {whisper_model} model...")
                transcriber_instance = WhisperTranscriber(model_size=whisper_model)

            def on_progress(pct, msg):
                update_transcribe_progress(pct, msg)

            target_lang = req.language
            if target_lang in ("auto", "", "None"):
                target_lang = None

            lyrics = transcriber_instance.transcribe(transcribe_path, language=target_lang, progress_callback=on_progress)
            detected_lang = getattr(transcriber_instance, "last_detected_language", target_lang or "en")
            source_type = "whisper"

        # Guard: If audio is Khmer but Whisper produced non-Khmer text (hallucinations like "I'm going to die")
        # and somehow the Magic DB failed earlier, we try to use text-only Gemini fallback.
        if (target_lang == "km" or is_khmer_text(req.audio_path)):
            sample_whisper = " ".join([l.get("text", "") for l in (lyrics or [])[:8]])
            if not is_khmer_text(sample_whisper):
                print(f"[KMVM Transcribe] ⚠️ Whisper produced non-Khmer hallucination on Khmer song: '{sample_whisper[:80]}'")
                try:
                    from backend.khmer_lyric_matcher import match_or_fetch_khmer_lyrics
                    base_t = os.path.splitext(os.path.basename(req.audio_path))[0]
                    c_title, c_artist = clean_youtube_title_and_artist(base_t, use_gemini=True)
                    gem_res = match_or_fetch_khmer_lyrics(req.audio_path, c_title, c_artist, progress_callback=update_transcribe_progress)
                    if gem_res:
                        lrc_p, _ = gem_res
                        lyrics = parse_subtitle_file(lrc_p)
                        detected_lang = "km"
                        source_type = "retrieved-timing"
                        print(f"[KMVM Transcribe] Replaced Whisper hallucination with {len(lyrics)} retrieved Khmer lines!")
                except Exception as fb_err:
                    print(f"[KMVM Transcribe] Gemini fallback notice: {fb_err}")

        if source_type == "retrieved-timing":
            # Retrieved sheets come with cloud timings; re-measure the words against the singer
            # audio so nothing guessed by the model is ever cached or drawn on stage.
            try:
                audio_p = _resolve_alignment_audio(req.audio_path)
                verified, _report, local_source = _align_selected_lyrics(lyrics, audio_p)
                lyrics, source_type = verified, local_source
            except HTTPException as align_notice:
                print(f"[KMVM Local Align] {align_notice.detail} — keeping the retrieved sheet as-is")

        lang_str = str(detected_lang).upper() if detected_lang else "SYNCED"

        # Auto-cache to matching .lrc file next to audio for instant 0s future loading
        if lyrics and len(lyrics) > 0:
            try:
                base_audio, _ = os.path.splitext(req.audio_path)
                lang_ext = f".{detected_lang}" if detected_lang else ".km"
                lrc_dest = f"{base_audio}{lang_ext}.lrc"
                export_lyrics_to_lrc(lyrics, lrc_dest)
                print(f"[KMVM Lyrics] 💾 Cached synced lyrics to {os.path.basename(lrc_dest)}")
            except Exception as cache_err:
                print(f"[KMVM Lyrics] Note on LRC caching: {cache_err}")

        update_transcribe_progress(100, f"Lyrics successfully transcribed ({lang_str})!")
        return {
            "status": "success",
            "source": source_type,
            "detected_language": detected_lang,
            "lyrics": lyrics,
            "count": len(lyrics)
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        update_transcribe_progress(0, f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

@app.post("/api/parse-lrc")
async def parse_lrc(req: LrcParseRequest):
    """Parses LRC, SRT, or VTT format lyrics with word-level interpolation and Khmer tokenization."""
    try:
        lyrics = parse_subtitle_content(req.lrc_text)
        return {
            "status": "success",
            "lyrics": lyrics,
            "count": len(lyrics)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LRC parse failed: {str(e)}")

@app.post("/api/lyrics/upload")
async def upload_lyrics_file(file: UploadFile = File(...)):
    """Uploads and parses an LRC, SRT, or VTT subtitle file."""
    try:
        content_bytes = await file.read()
        content = content_bytes.decode("utf-8", errors="ignore")
        lyrics = parse_subtitle_content(content)
        return {
            "status": "success",
            "filename": file.filename,
            "lyrics": lyrics,
            "count": len(lyrics)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse uploaded subtitle file: {str(e)}")

@app.post("/api/lyrics/verify")
def verify_lyrics_api(req: LyricsVerifyRequest):
    try:
        lyrics = req.lyrics_data or []
        if req.audio_path:
            audio_p = _resolve_alignment_audio(req.audio_path)
            verified, report, source = _align_selected_lyrics(lyrics, audio_p)
            _save_aligned_subtitles(verified, audio_p)
        else:
            verified, report = double_check_lyrics(lyrics, preserve_text=True)
            report.pop("confidence", None)
            report["status"] = "Timestamp structure checked; no singer audio was checked"
            source = "timestamp_validation"
        return {
            "status": "success",
            "verified": True,
            "source": source,
            "lines_count": len(verified),
            "words_count": report.get("total_words", 0),
            "corrections_made": report.get("corrections_count", 0),
            "report": report,
            "lyrics": verified,
            "srt_content": export_subtitles_to_srt(verified)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lyrics verification error: {str(e)}")

@app.post("/api/lyrics/auto_fix")
def auto_fix_lyrics_api(req: LyricsVerifyRequest):
    """Passes the transcribed lyrics through the local LLM to fix phonetic/contextual errors."""
    try:
        from backend.llm_engine import llm_engine
        # 1. Run LLM Auto-Correction Pipeline
        llm_fixed = llm_engine.auto_correct_transcription(req.lyrics_data)
        # 2. Run standard verification to re-interpolate missing/changed words
        verified, report = double_check_lyrics(llm_fixed)
        return {
            "status": "success",
            "verified": True,
            "lyrics": verified,
            "report": report
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Auto-Fix Error: {str(e)}")

@app.post("/api/lyrics/correct-with-reference")
def correct_lyrics_with_reference_api(req: LyricsCorrectReferenceRequest):
    t_start = time.time()
    if not req.reference_text or not req.reference_text.strip():
        raise HTTPException(status_code=400, detail="Please paste reference lyrics text")

    audio_p = _resolve_alignment_audio(req.audio_path)
    audio_label = os.path.basename(audio_p) if audio_p else "None"
    print(f"\n[Lyrics Align] 🎵 Align Request Received: audio='{audio_label}'", flush=True)

    speaker_tag_pat = r'^\s*[\(\[]\s*(?:ស្រី|ប្រុស|ស្រីនិងប្រុស|ប្រុសនិងស្រី|រួមគ្នា|ស្រី/ប្រុស|ប្រុស/ស្រី|F|M|Male|Female|Singer)\s*[\)\]]\s*'
    raw_lines = [l.strip() for l in req.reference_text.splitlines() if l.strip()]
    ref_lines = []
    for l in raw_lines:
        if re.match(r'^\[(?:ti|ar|al|by|offset|length|re|ve):.*?\]', l, re.IGNORECASE):
            continue
        cleaned = re.sub(r'^(?:#+|\*+|-+|\d+[\.\)]|[A-Za-z]+\s*\d+:)\s*', '', l).strip()
        cleaned = re.sub(r'^\[\d{1,2}:\d{2}(?:\.\d+)?\]\s*', '', cleaned)
        cleaned = re.sub(r'^\d{2}:\d{2}(?:\.\d+)?\s*-->\s*\d{2}:\d{2}(?:\.\d+)?\s*', '', cleaned)
        cleaned = re.sub(speaker_tag_pat, '', cleaned, flags=re.IGNORECASE).strip()
        if cleaned:
            # Filter pure non-lyric noise/instrumental markers like ((((( ... ភ្លេង ... ))))), [Music], (Solo)
            if re.match(r'^\s*[\(\[\{<~-]*\s*(?:\.{2,}|…|-+|\*+)?\s*(?:ភ្លេង|តន្ត្រី|music|solo|instrumental|guitar\s*solo|intro|outro|bridge)\s*(?:\.{2,}|…|-+|\*+)?\s*[\)\]\}>~-]*\s*$', cleaned, re.IGNORECASE):
                continue
            # Filter lines that only contain punctuation / parentheses / dots
            if re.match(r'^[()\[\]{}<>\s.…·\-–—~:;!?។៕,]+$', cleaned):
                continue
            ref_lines.append(cleaned)

    if not ref_lines:
        print("[Lyrics Align] ❌ No readable lyric lines found in pasted text", flush=True)
        raise HTTPException(status_code=400, detail="No readable lyric lines found in pasted text")

    print(f"[Lyrics Align] 📝 Parsed {len(ref_lines)} lyric lines (from {len(raw_lines)} raw lines)", flush=True)
    print(f"[Lyrics Align] 🎙️ Aligning lines to singing vocals & calculating word cadences...", flush=True)

    try:
        aligned_lyrics, report, source_used = _align_selected_lyrics(
            [{"text": text} for text in ref_lines], audio_p
        )
        _save_aligned_subtitles(aligned_lyrics, audio_p, force_replace_srt=True)
        elapsed = time.time() - t_start
        print(f"[Lyrics Align] ✅ Successfully aligned {len(aligned_lyrics)} lines in {elapsed:.2f}s ({source_used})\n", flush=True)

        return {
            "status": "success",
            "lines_count": len(aligned_lyrics),
            "changes_count": len(aligned_lyrics),
            "source": source_used,
            "report": report,
            "lyrics": aligned_lyrics
        }
    except Exception as e:
        elapsed = time.time() - t_start
        print(f"[Lyrics Align] ❌ Alignment error after {elapsed:.2f}s: {e}\n", flush=True)
        raise

class SubtitleSaveRequest(BaseModel):
    lyrics_data: List[Dict[str, Any]]
    audio_path: Optional[str] = None

@app.post("/api/subtitles/save")
async def save_subtitles_api(req: SubtitleSaveRequest):
    """Saves updated subtitle timing and cues to companion .lrc and .srt files."""
    audio_p = req.audio_path
    if audio_p:
        clean_rel = audio_p.replace("\\", "/").lstrip("/")
        candidates = [
            audio_p,
            os.path.abspath(audio_p),
            os.path.join(AUDIO_DIR, os.path.basename(audio_p)),
            os.path.join(UPLOAD_DIR, "audio", os.path.basename(audio_p)),
            os.path.join(os.path.dirname(AUDIO_DIR), clean_rel)
        ]
        audio_p = next((c for c in candidates if c and os.path.exists(c)), None)
    if not audio_p and os.path.exists(AUDIO_DIR):
        all_audios = [
            os.path.join(AUDIO_DIR, f) for f in os.listdir(AUDIO_DIR)
            if f.lower().endswith(('.mp3', '.wav', '.flac', '.m4a', '.ogg'))
        ]
        if all_audios:
            all_audios.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            audio_p = all_audios[0]

    if audio_p and req.lyrics_data:
        try:
            base_audio, _ = os.path.splitext(audio_p)
            for ext in (".lrc", ".km.lrc"):
                export_lyrics_to_lrc(req.lyrics_data, f"{base_audio}{ext}")
            srt_str = export_subtitles_to_srt(req.lyrics_data)
            for ext in (".srt", ".km.srt"):
                with open(f"{base_audio}{ext}", "w", encoding="utf-8") as sf:
                    sf.write(srt_str)
            return {"status": "success", "file": base_audio, "count": len(req.lyrics_data)}
        except Exception as e:
            return {"status": "error", "detail": str(e)}
    return {"status": "ok", "count": len(req.lyrics_data or [])}

class TranslateLinesRequest(BaseModel):
    lines: List[str]
    target_lang: str = "English"
    song_title: str = ""
    artist: str = ""
    # Khmer only: when True (default) every line that still reads word-for-word gets one
    # focused native-rewrite pass before it comes back. Set False to save one AI request.
    polish: bool = True

class RefineKhmerLinePair(BaseModel):
    id: int
    original: Optional[str] = ""
    khmer: Optional[str] = ""

class RefineKhmerLyricsRequest(BaseModel):
    pairs: List[RefineKhmerLinePair]
    song_title: Optional[str] = ""
    artist: Optional[str] = ""
    source_lang: Optional[str] = None

class TranslationSaveRequest(BaseModel):
    audio_path: Optional[str] = None
    lang: str = "en"
    lines: List[str] = []
    lyrics_data: Optional[List[Dict[str, Any]]] = None  # timing source (original cues)

def _resolve_audio_path(audio_p: Optional[str]) -> Optional[str]:
    if audio_p:
        clean_rel = audio_p.replace("\\", "/").lstrip("/")
        candidates = [
            audio_p,
            os.path.abspath(audio_p),
            os.path.join(AUDIO_DIR, os.path.basename(audio_p)),
            os.path.join(UPLOAD_DIR, "audio", os.path.basename(audio_p)),
            os.path.join(os.path.dirname(AUDIO_DIR), clean_rel),
        ]
        hit = next((c for c in candidates if c and os.path.exists(c)), None)
        if hit:
            return hit
    if os.path.exists(AUDIO_DIR):
        all_audios = [
            os.path.join(AUDIO_DIR, f) for f in os.listdir(AUDIO_DIR)
            if f.lower().endswith(('.mp3', '.wav', '.flac', '.m4a', '.ogg'))
        ]
        if all_audios:
            all_audios.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            return all_audios[0]
    return None


# Translated tracks NEVER live at "<song>.<lang>.srt": the studio treats those filenames as
# ORIGINAL cue sheets, so an English translation of a Vietnamese song could be loaded as the
# original. Every translation gets a "-tr" tag (".km-tr.srt", ".en-tr.srt", ...), which the
# original-subtitle finder always ignores.
TRANSLATION_FILE_TAGS = {}
TRANSLATION_LANG_FROM_TAG = {"km-tr": "km"}


def _translation_tag(lang: str) -> str:
    """Filename tag for a translated track language code (always "<lang>-tr")."""
    code = re.sub(r'[^a-z0-9_\-]', '', str(lang or 'en').lower()) or 'en'
    return TRANSLATION_FILE_TAGS.get(code, f"{code}-tr")


def _translation_srt_path(audio_p: str, lang: str) -> str:
    """Absolute path of the companion SRT holding the translated lyric track."""
    base_audio, _ = os.path.splitext(audio_p)
    return f"{base_audio}.{_translation_tag(lang)}.srt"


def build_translation_display_lyrics(lyrics: List[Dict[str, Any]], mode: str,
                                     translation_lines: Optional[List[str]]) -> List[Dict[str, Any]]:
    """
    Returns a DISPLAY-ONLY copy of the cue list for 'translation_only' mode.
    The original cues (text, timings, word timestamps) and the original SRT on disk are
    never mutated — only the copy handed to the renderer gets the translated text, and it
    keeps the exact same start/end window so the track stays locked to the singer.
    """
    if mode != "translation_only" or not lyrics or not translation_lines:
        return lyrics
    out = []
    for i, line in enumerate(lyrics):
        translated = str(translation_lines[i]).strip() if i < len(translation_lines) and translation_lines[i] else ""
        copied = dict(line)
        if translated:
            s = float(line.get("start", 0.0))
            e = float(line.get("end", s + 3.0))
            copied["text"] = translated
            copied["words"] = compute_weighted_word_timestamps(tokenize_line_words(translated), s, max(e, s + 0.4))
        out.append(copied)
    return out

def _naturalness_cues(lines):
    """Per-line Khmer naturalness grades, for the editor to mark the lines a human should review."""
    cues = []
    for i, l in enumerate(lines or []):
        nat = l.get("naturalness") if isinstance(l, dict) else None
        if not nat:
            continue
        cues.append({
            "id": i,
            "status": str(nat.get("status") or ""),
            "issues": [str(x) for x in (nat.get("issues") or [])],
        })
    return cues

def _gemini_service_notice() -> str:
    """Why the last Gemini call could not answer, as one honest sentence — '' when it did."""
    try:
        from backend.llm_engine import get_last_gemini_status
        code, info = get_last_gemini_status()
    except Exception:
        return ""
    if code == 429:
        return "Gemini is rate-limiting this key (HTTP 429 — the quota is used up)"
    if code:
        return f"Gemini refused the request (HTTP {code}{', ' + info if info else ''})"
    if info:
        return f"Gemini could not be reached ({info})"
    return ""

@app.post("/api/lyrics/translate-lines")
def translate_lyrics_lines_api(req: TranslateLinesRequest):
    """AI-translates lyric lines to any target language, preserving 1:1 line order.

    For a Khmer target the result is additionally graded for naturalness and any line that
    still reads word-for-word (or leaks foreign letters, or is too long to sing) gets one
    focused native rewrite. The counts come back so the studio can tell the user honestly.
    """
    lines = [str(l) for l in (req.lines or [])]
    if not lines:
        return {"status": "success", "lines": []}
    try:
        payload = [{"line_id": i, "text": t} for i, t in enumerate(lines)]
        translated = llm_engine.translate_lyrics_data(
            payload,
            target_lang=req.target_lang or "English",
            song_title=req.song_title or "",
            artist=req.artist or "",
            auto_polish=req.polish,
        )
        out = [str(l.get("text", "")) for l in translated]
        unchanged = sum(1 for a, b in zip(out, lines) if a.strip() == b.strip())
        if unchanged == len(lines):
            # Three different failures look identical from here — a dead key, a spent quota, or a
            # model that echoed the input back — and only the last one is worth re-pressing.
            reason = ""
            try:
                from backend.khmer_lyric_matcher import get_last_key_error
                reason = str(get_last_key_error() or "")
            except Exception:
                pass
            notice = _gemini_service_notice()
            if reason:
                detail = f"Translation failed: {reason}"
            elif notice:
                detail = f"{notice}. Wait a moment, then press the button again."
            else:
                detail = ("Gemini answered but repeated the original lines instead of translating. "
                          "Try again in a moment.")
            return {"status": "error", "detail": detail}
        summary = llm_engine.khmer_naturalness_summary(translated)
        return {
            "status": "success",
            "lines": out,
            "target_lang": req.target_lang,
            "khmer_natural": summary["natural"],
            "khmer_polished": summary["polished"],
            "khmer_literal": summary["still_literal"],
            "khmer_naturalness": _naturalness_cues(translated),
            "service_notice": _gemini_service_notice(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")

@app.post("/api/lyrics/refine-khmer")
def refine_khmer_lyrics_api(req: RefineKhmerLyricsRequest):
    """
    AI-Powered Native Khmer Refinement API:
    Rewrites translated Khmer lyrics into natural, singable, native Khmer like a song
    originally composed in Khmer, fixing literal/machine translations, unnatural phrasing,
    and preserving exact 1:1 line ordering and timestamps.
    """
    if not req.pairs:
        return {"status": "success", "lines": []}
    try:
        from backend.llm_engine import llm_engine
        payload = [
            {"id": p.id, "original": p.original or "", "khmer": p.khmer or ""}
            for p in req.pairs
        ]
        refined = llm_engine.refine_khmer_lyrics(
            pairs=payload,
            song_title=req.song_title or "",
            artist=req.artist or "",
            source_lang=req.source_lang
        )
        summary = llm_engine.khmer_naturalness_summary(refined)
        return {
            "status": "success",
            "lines": refined,
            "khmer_natural": summary["natural"],
            "khmer_polished": summary["polished"],
            "khmer_literal": summary["still_literal"],
            "khmer_naturalness": [
                {
                    "id": p.get("id", i),
                    "status": str((p.get("naturalness") or {}).get("status") or ""),
                    "issues": [str(x) for x in ((p.get("naturalness") or {}).get("issues") or [])],
                }
                for i, p in enumerate(refined)
            ],
            "service_notice": _gemini_service_notice(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Khmer refinement failed: {str(e)}")

@app.post("/api/lyrics/translation/save")
async def save_translation_api(req: TranslationSaveRequest):
    """
    Saves the translated lyric track as a SEPARATE companion SRT (e.g. song.en-tr.srt) that
    reuses the original cues' timestamps and sequence verbatim. The original .srt/.km.srt is
    untouched, and the "-tr" tag keeps the translation out of original-subtitle discovery.
    """
    lang = re.sub(r'[^a-z0-9_\-]', '', (req.lang or 'en').lower()) or 'en'
    audio_p = _resolve_audio_path(req.audio_path)
    if not audio_p:
        raise HTTPException(status_code=400, detail="Audio file not found for translation save")

    # Timing source: explicit original cues (kept index-aligned with req.lines),
    # else the original SRT on disk. Empty lines still consume their index so the
    # translated track stays 1:1 with the original cue sequence.
    timings = [dict(l) for l in (req.lyrics_data or [])]
    if not timings:
        base_audio, _ = os.path.splitext(audio_p)
        for ext in (".km.srt", ".srt"):
            src = f"{base_audio}{ext}"
            if os.path.exists(src):
                with open(src, "r", encoding="utf-8") as sf:
                    timings = parse_subtitle_content(sf.read())
                break

    cues = []
    for i, text in enumerate(req.lines or []):
        if not str(text).strip():
            continue
        if i < len(timings):
            src = timings[i]
            start = float(src.get("start", 0.0))
            end = float(src.get("end", start + 2.0))
        elif cues:
            start = cues[-1]["end"] + 0.05
            end = start + 2.0
        else:
            start, end = 0.0, 2.0
        cues.append({"line_id": len(cues), "start": round(start, 2), "end": round(end, 2), "text": str(text).strip()})

    if not cues:
        raise HTTPException(status_code=400, detail="No translated lines to save")

    base_audio, _ = os.path.splitext(audio_p)
    out_path = _translation_srt_path(audio_p, lang)
    srt_str = export_subtitles_to_srt(cues)
    with open(out_path, "w", encoding="utf-8") as sf:
        sf.write(srt_str)
    return {"status": "success", "file": out_path, "lang": lang, "count": len(cues), "srt_content": srt_str}

@app.get("/api/lyrics/translation")
async def get_translation_api(audio_path: str = "", lang: str = "en"):
    """Loads a saved translated track (text lines in original cue order + their timings)."""
    audio_p = _resolve_audio_path(audio_path or None)
    if not audio_p:
        return {"status": "success", "lines": [], "cues": [], "langs": []}
    base_audio, _ = os.path.splitext(audio_p)
    path = _translation_srt_path(audio_p, lang)
    if not os.path.exists(path) and lang.lower() != "km":
        # Backward compatibility with tracks saved before the "-tr" tag existed.
        legacy = f"{base_audio}.{lang.lower()}.srt"
        if os.path.exists(legacy):
            path = legacy
    lines, cues = [], []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as sf:
            parsed = parse_subtitle_content(sf.read())
        cues = [{"line_id": i, "start": float(c.get("start", 0.0)), "end": float(c.get("end", 0.0)),
                 "text": c.get("text", "")} for i, c in enumerate(parsed)]
        lines = [c["text"] for c in cues]
    return {"status": "success", "lines": lines, "cues": cues, "lang": lang.lower(),
            "file": path if os.path.exists(path) else None}

@app.get("/api/lyrics/translation/list")
async def list_translations_api(audio_path: str = ""):
    """Lists which translated tracks exist for the current song."""
    audio_p = _resolve_audio_path(audio_path or None)
    if not audio_p:
        return {"status": "success", "langs": []}
    base_audio, _ = os.path.splitext(audio_p)
    prefix = os.path.basename(base_audio) + "."
    langs = []
    d = os.path.dirname(base_audio)
    for f in os.listdir(d):
        if f.startswith(prefix) and f.endswith(".srt"):
            mid = f[len(prefix):-4]
            if not mid or "." in mid:
                continue
            if mid == "km":
                # "<song>.km.srt" is the ORIGINAL Khmer cue sheet, never a translation track
                continue
            if mid.endswith("-tr"):
                langs.append(mid[:-3])
            else:
                # Legacy tracks saved before the "-tr" tag existed.
                langs.append(TRANSLATION_LANG_FROM_TAG.get(mid, mid))
    return {"status": "success", "langs": sorted(set(langs))}

@app.post("/api/subtitles/export")
async def export_subtitles_api(req: SubtitleExportRequest):
    try:
        fmt = (req.format or "srt").lower().strip().lstrip(".")
        safe_title = re.sub(r'[^a-zA-Z0-9_\-\u1780-\u17FF]', '_', (req.title or "subtitles")).strip('_') or "subtitles"
        
        if fmt in ("capcut", "capcut_srt", "capcutsrt"):
            content = format_srt_for_capcut(req.lyrics_data or [])
            filename = f"{safe_title}_CapCut.srt"
            fmt_res = "srt"
        else:
            content = export_subtitles_content(
                lyrics=req.lyrics_data or [],
                format_type=fmt,
                title=req.title or "VIDA Studio Subtitles",
                artist=req.artist or ""
            )
            filename = f"{safe_title}.{fmt}"
            fmt_res = fmt

        mime_types = {
            "srt": "text/plain; charset=utf-8",
            "vtt": "text/vtt; charset=utf-8",
            "lrc": "text/plain; charset=utf-8",
            "ass": "text/plain; charset=utf-8",
            "ssa": "text/plain; charset=utf-8",
            "txt": "text/plain; charset=utf-8"
        }
        mime = mime_types.get(fmt_res, "text/plain; charset=utf-8")

        return {
            "status": "success",
            "format": fmt_res,
            "filename": filename,
            "mime_type": mime,
            "content": content,
            "cues_count": len(req.lyrics_data or [])
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Subtitle export failed: {str(e)}")

@app.post("/api/subtitles/export-capcut")
async def export_subtitles_capcut_api(req: SubtitleExportRequest):
    """
    Dedicated CapCut Subtitle Exporter:
    Generates 100% CapCut-compatible, studio-grade SubRip (.srt) subtitle file:
    - Zero backward drift, strictly non-overlapping cues.
    - Word-boundary line breaking optimized for 9:16 and 16:9 safe zones.
    - 100% Khmer Unicode normalization (no dotted-circle rendering artifacts).
    """
    try:
        content = format_srt_for_capcut(req.lyrics_data or [])
        safe_title = re.sub(r'[^a-zA-Z0-9_\-\u1780-\u17FF]', '_', (req.title or "lyrics")).strip('_') or "lyrics"
        filename = f"{safe_title}_CapCut.srt"
        return {
            "status": "success",
            "format": "srt",
            "filename": filename,
            "mime_type": "text/plain; charset=utf-8",
            "content": content,
            "cues_count": len(req.lyrics_data or [])
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CapCut export failed: {str(e)}")

@app.post("/api/subtitles/ai-fix")
def ai_fix_subtitles_api(req: SubtitleAIFixRequest):
    """
    AI Core Subtitle Enhancer:
    1. Repairs phonetic and Khmer orthography errors using Gemini AI / LLM engine.
    2. Acoustically aligns timestamps to vocal singing activity if audio_path is provided.
    3. Runs 100% double-check verification to guarantee strictly monotonic non-overlapping timings.
    4. Generates instant verified SRT content.
    """
    try:
        lyrics = req.lyrics_data or []
        if not lyrics:
            return {"status": "success", "verified": True, "lyrics": [], "report": {}, "count": 0}

        # Step 1: AI Auto-Correction Pipeline
        from backend.llm_engine import llm_engine
        try:
            llm_fixed = llm_engine.auto_correct_transcription(lyrics)
        except Exception as e:
            print(f"[AI Subtitle Fix] LLM step notice: {e}")
            llm_fixed = lyrics

        source = "timestamp_validation"
        audio_p = None
        if req.align_vocals:
            audio_p = _resolve_alignment_audio(req.audio_path)
            verified, report, source = _align_selected_lyrics(llm_fixed, audio_p)
        else:
            verified, report = double_check_lyrics(llm_fixed, preserve_text=True)
            report.pop("confidence", None)
            report["status"] = "Timestamp structure checked; no singer audio was checked"
        srt_content = export_subtitles_to_srt(verified)
        if audio_p:
            _save_aligned_subtitles(verified, audio_p)

        return {
            "status": "success",
            "verified": True,
            "source": source,
            "count": len(verified),
            "corrections_made": report.get("corrections_count", 0),
            "report": report,
            "lyrics": verified,
            "srt_content": srt_content
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Subtitle Fix failed: {str(e)}")

def _resolve_alignment_audio(audio_path: Optional[str]) -> str:
    if not audio_path:
        raise HTTPException(status_code=400, detail="Select an audio track before syncing lyrics")
    decoded = urllib.parse.unquote(audio_path).replace("\\", "/")
    candidates = [decoded, os.path.join(AUDIO_DIR, os.path.basename(decoded))]
    audio_p = next((p for p in candidates if os.path.isfile(p)), None)
    if not audio_p:
        raise HTTPException(status_code=404, detail="Selected audio file not found")
    return os.path.abspath(audio_p)


def _align_selected_lyrics(lyrics: List[Dict[str, Any]], audio_p: str, progress_callback=None):
    from backend.audio_analyzer import decode_audio_to_numpy
    import math

    if progress_callback:
        progress_callback(30, "Analyzing audio signal & frequency spectrum...")
    texts = [str(line.get("text", "")).strip() for line in lyrics]
    if not texts or not all(texts):
        raise HTTPException(status_code=400, detail="Every lyric line must contain text")
    _, _, duration = decode_audio_to_numpy(audio_p, target_sr=8000)
    if progress_callback:
        progress_callback(45, "Acoustic VAD: Detecting vocal phrases & onsets...")
    aligned = force_align_lyrics_to_audio(texts, audio_p, duration)
    if progress_callback:
        progress_callback(85, "Checking cadence & verifying syllable boundaries...")
    if not aligned or [line.get("text") for line in aligned] != texts:
        raise HTTPException(status_code=422, detail="Could not align every original lyric line to this audio; lyrics were not replaced")
    verified, report = double_check_lyrics(aligned, preserve_text=True)
    if [line["text"] for line in verified] != texts:
        raise HTTPException(status_code=422, detail="Alignment changed the original lines; lyrics were not replaced")
    if progress_callback:
        progress_callback(95, "Validating word timestamps & precision...")
    for original, line in zip(lyrics, verified):
        ls = float(line.get("start", 0.0))
        le = float(line.get("end", ls + 2.0))
        if not (math.isfinite(ls) and math.isfinite(le) and 0 <= ls < le <= duration):
            ls = max(0.0, min(ls, max(0.0, duration - 0.4)))
            le = max(ls + 0.35, min(le, duration if duration > 0 else ls + 2.0))
            line["start"] = round(ls, 2)
            line["end"] = round(le, 2)
        else:
            line["start"] = round(ls, 2)
            line["end"] = round(le, 2)

        words = line.get("words", [])
        if words:
            w_cur = line["start"]
            for wi, w in enumerate(words):
                ws = float(w.get("start", w_cur))
                we = float(w.get("end", ws + 0.1))
                if not (math.isfinite(ws) and math.isfinite(we)):
                    ws, we = w_cur, w_cur + 0.1
                ws = max(w_cur, min(ws, max(w_cur, line["end"] - 0.04)))
                we = max(ws + 0.04, min(we, line["end"]))
                w["start"] = round(ws, 2)
                w["end"] = round(we, 2)
                w_cur = w["end"]
            if words[-1]["end"] > line["end"]:
                line["end"] = words[-1]["end"]

        line["line_id"] = original.get("line_id", line.get("line_id", 0))
    for line, aligned_line in zip(verified, aligned):
        if "confidence" in aligned_line:
            line["confidence"] = aligned_line["confidence"]
    source = "ctc_word_alignment" if all("confidence" in line for line in aligned) else "acoustic_estimate"
    if source == "acoustic_estimate":
        from backend.vocal_align import detect_vocal_segments
        if len(detect_vocal_segments(audio_p)) < 2:
            raise HTTPException(status_code=422, detail="No reliable singing phrases detected; lyrics were not replaced")
    report.pop("confidence", None)
    report["status"] = "Timestamp structure checked; singing accuracy requires playback review"
    return verified, report, source


def _save_aligned_subtitles(lyrics: List[Dict[str, Any]], audio_p: str, force_replace_srt: bool = False):
    base_audio = os.path.splitext(audio_p)[0]
    suffixes = ("", ".km") if detect_text_language(" ".join(line["text"] for line in lyrics)) == "km" else ("",)
    srt_content = export_subtitles_to_srt(lyrics)
    # Caption parsers drop bracket punctuation, so compare bare words only.
    cue_words = lambda cues: [re.sub(r"[^\w\s]+", "", c["text"], flags=re.UNICODE).strip().lower() for c in cues]
    new_texts = cue_words(lyrics)
    for suffix in suffixes:
        export_lyrics_to_lrc(lyrics, f"{base_audio}{suffix}.lrc")
        srt_path = f"{base_audio}{suffix}.srt"
        if not force_replace_srt and os.path.exists(srt_path):
            # Only refresh an .srt that holds these same words unless forced.
            try:
                existing = cue_words(parse_subtitle_file(srt_path))
            except Exception:
                existing = None
            if existing != new_texts:
                continue
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)


@app.post("/api/subtitles/align-audio")
def align_subtitles_to_audio_api(req: SubtitleAIFixRequest):
    try:
        if not req.lyrics_data:
            raise HTTPException(status_code=400, detail="Load lyrics before syncing")
        audio_p = _resolve_alignment_audio(req.audio_path)
        verified, report, source = _align_selected_lyrics(req.lyrics_data, audio_p)
        _save_aligned_subtitles(verified, audio_p)
        return {
            "status": "success",
            "source": source,
            "count": len(verified),
            "lyrics": verified,
            "report": report,
            "srt_content": export_subtitles_to_srt(verified)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vocal subtitle alignment error: {str(e)}")


def clean_youtube_title_and_artist(
    raw_title: str,
    uploader: Optional[str] = None,
    raw_artist: Optional[str] = None,
    use_gemini: bool = True
) -> tuple[str, str]:
    """
    Intelligently splits and cleans YouTube video titles into (clean_title, clean_artist/singer).
    Uses Gemini AI if available to parse complex, messy, or reversed titles.
    Strips noise like [Official MV], (Lyrics Video), 4K, HD, etc.
    Supports both English and Khmer conventions (e.g. 'បទ៖ ... ច្រៀងដោយ ...').
    """
    if not raw_title:
        return "Untitled Track", (uploader or "Unknown Artist")

    channel = uploader or raw_artist or ""

    # 1. Ask Gemini AI for intelligent semantic extraction (accurate, no reversed fields)
    if use_gemini:
        try:
            try:
                from backend.khmer_lyric_matcher import gemini_clean_youtube_metadata
            except ImportError:
                from khmer_lyric_matcher import gemini_clean_youtube_metadata
            gem_res = gemini_clean_youtube_metadata(raw_title, uploader=channel)
            if gem_res:
                g_title, g_artist, _ = gem_res
                if g_title and g_artist:
                    return g_title, g_artist
        except Exception as gem_err:
            print(f"[Gemini Metadata Parser] Notice: {gem_err}. Using rule-based cleaner.")
    
    t = raw_title.strip()
    # Normalize Windows/Unicode fullwidth characters (e.g. yt-dlp replacing | with ｜ on Windows)
    t = t.replace('｜', '|').replace('：', ':').replace('／', '/').replace('＼', '\\').replace('〜', '~')
    kh_match = re.search(r'បទ[\s:៖]+(.*?)(?:ច្រៀងដោយ[\s:៖]+|\s*-\s*)(.*)', t, re.IGNORECASE)
    if kh_match:
        cand_title = kh_match.group(1).strip()
        cand_artist = kh_match.group(2).strip()
        cand_title = re.sub(r'\[.*?\]|\(.*?\)|【.*?】', '', cand_title).strip()
        cand_artist = re.sub(r'\[.*?\]|\(.*?\)|【.*?】', '', cand_artist).strip()
        if cand_title and cand_artist:
            return cand_title, cand_artist

    # 2. Strip bracketed noise keywords and trailing video labels (e.g. I Video Animation, | Official MV)
    bracket_keywords = r'official|video|mv|audio|lyric|lyrics|hd|4k|remix|slowed|reverb|full|clip|cover|dance|version|ost|teaser|visualizer|original'
    t = re.sub(r'\[[^\]]*(?:' + bracket_keywords + r')[^\]]*\]', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'\([^\)]*(?:' + bracket_keywords + r')[^\)]*\)', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'【[^】]*(?:' + bracket_keywords + r')[^】]*】', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'[\s|I]+(?:Video\s*Animation|Official.*|MV|Audio|Visualizer|Full\s*Song|Remix).*$', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'\|\s*[^|]*(?:' + bracket_keywords + r')[^|]*$', '', t, flags=re.IGNORECASE).strip()
    t = t.strip(' -–—|:~#_')

    # 3. Delimiter split into (Artist, Title) with Khmer-aware Title - Artist support
    split_match = re.split(r'\s*[-–—|~]\s*', t, maxsplit=1)
    
    artist = ""
    title = ""
    
    if len(split_match) == 2:
        part1, part2 = split_match[0].strip(), split_match[1].strip()
        quote_match = re.match(r'^["\'](.*?)["\']$', part2)
        if quote_match:
            artist = part1
            title = quote_match.group(1).strip()
        elif is_khmer_text(part1) or is_khmer_text(part2):
            # In Khmer music, standard YouTube upload convention is [Song Title] - [Singer / Artist]
            known_singers = [
                "សុីន សុីសាមុត", "ស៊ីន ស៊ីសាមុត", "ស៊ីន​ ស៊ីសាមុត", "សុីន​ សុីសាមុត", "ស៊ិន ស៊ីសាមុត",
                "រស់ សេរីសុទ្ធា", "ប៉ែន រ៉ន", "ហួយ មាស", "អ៊ឹង ណារី", "មាស សាម៉ន", "ព្រាប សុវត្ថិ",
                "ខេមរៈ សិរីមន្ត", "មាស សុខសោភា", "តន់ ចន្ទសីម៉ា", "ខេម", "G-Devith", "VannDa", "វ៉ាន់ដា",
                "យឿន ពិសី", "ឱក សុគន្ធកញ្ញា", "ឆន សុវណ្ណារាជ", "សុគន្ធ និសា", "ពេជ្រ សោភា", "កែវ វាសនា",
                "គូម៉ា", "កែវ សារ៉ាត់", "សាមុត", "សេរីសុទ្ធា"
            ]
            p2_is_singer = any(s.lower() in part2.lower() for s in known_singers) or bool(re.search(r'ច្រៀងដោយ|ដោយ|feat|ft\.', part2, re.IGNORECASE))
            p1_is_singer = any(s.lower() in part1.lower() for s in known_singers)
            
            if p2_is_singer or (not p1_is_singer):
                title = part1
                artist = re.sub(r'^(?:ច្រៀងដោយ|ដោយ|singer|artist)[\s:៖]+', '', part2, flags=re.IGNORECASE).strip()
            else:
                artist = part1
                title = part2
        else:
            artist = part1
            title = part2
    else:
        title = t
        if raw_artist and raw_artist.lower() not in ["youtube artist", "unknown", "various artists"]:
            artist = raw_artist
        elif uploader:
            artist = re.sub(r'(\s*-\s*Topic|VEVO|\s*Official|\s*Channel)$', '', uploader, flags=re.IGNORECASE).strip()
        else:
            artist = "Official Audio"

    title = title.strip(' "\'“”')
    artist = artist.strip(' "\'“”')
    return title or "VIDA Track", artist or "VIDA Artist"


def build_safe_audio_filename(title: str, artist: str = "", ext: str = ".mp3", max_length: int = 120) -> str:
    """
    Builds a clean, human-readable, and Windows-safe filename for music tracks.
    Format: 'Title - Artist.mp3' or 'Title.mp3' (if artist already in title or generic).
    Guarantees:
    - Strips all Windows-forbidden characters (< > : " / \\ | ? *)
    - Strips web/URL-breaking characters (# % &)
    - Strips emojis and trailing periods/spaces
    - Enforces Khmer Unicode NFC normalization
    - Restricts length to prevent Windows MAX_PATH violations
    """
    import unicodedata
    title = unicodedata.normalize('NFC', (title or "").strip(' ~\'"-_·“”.'))
    artist = unicodedata.normalize('NFC', (artist or "").strip(' ~\'"-_·“”.'))

    # Strip prefixes like 'ច្រៀងដោយ', 'Singer:', 'by'
    artist = re.sub(r'^(?:ច្រៀងដោយ|ដោយ|singer|artist|ft\.|feat\.)[\s:៖~]+', '', artist, flags=re.IGNORECASE).strip(' ~\'"-_·.')

    generic_artists = {
        "vida artist", "unknown", "unknown artist", "official audio", "official",
        "topic", "various artists", "youtube artist", "artist", "singer", "audio"
    }
    has_artist = bool(artist and artist.lower() not in generic_artists)
    if has_artist:
        if artist.lower() in title.lower():
            raw_base = title
        else:
            raw_base = f"{title} - {artist}"
    else:
        raw_base = title or "VIDA Track"

    # Normalize separators
    cleaned = raw_base.replace(":", " - ").replace("/", "-").replace("\\", "-").replace("|", " - ")
    # Strip Windows illegal chars and URL breakers
    cleaned = re.sub(r'[<>:"/\\|?*#%]+', '', cleaned)
    # Strip emojis and symbols outside BMP
    cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', cleaned)
    # Normalize hyphens and whitespace
    cleaned = re.sub(r'[\s\-~]+-[\s\-~]+', ' - ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' .-_~')

    if not cleaned:
        cleaned = "VIDA Track"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(' .-_~')
    if not ext.startswith("."):
        ext = "." + ext
    return f"{cleaned}{ext}"


@app.post("/api/youtube")
def download_youtube(req: YouTubeRequest):
    """Downloads audio from a YouTube URL via yt-dlp with auto subtitle extraction."""
    raw_url = req.url.strip()
    print(f"[KMVM YouTube] Received URL: '{raw_url}'")

    clean_u = extract_youtube_url(raw_url)
    if not clean_u and not raw_url.startswith("http"):
        clean_u = extract_youtube_url("https://" + raw_url)

    if not clean_u:
        print(f"[KMVM YouTube] Rejected URL: '{raw_url}'")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid YouTube link or ID: '{raw_url[:60]}'. Please provide a valid YouTube URL or video ID."
        )

    print(f"[KMVM YouTube] Downloading canonical URL: {clean_u}")
    update_youtube_progress(5, "Connecting to YouTube stream...")
    try:
        saved_path, info = download_youtube_audio(clean_u, output_dir=AUDIO_DIR, on_progress=update_youtube_progress)
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"[KMVM FATAL ERROR] {err}", flush=True)
        update_youtube_progress(0, f"Download error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Download error: {str(e)}")

    try:
        if not saved_path or not os.path.exists(saved_path):
            update_youtube_progress(0, "Failed to extract audio stream.")
            raise HTTPException(status_code=500, detail="Failed to extract audio stream from YouTube.")
        
        update_youtube_progress(90, "🤖 Gemini AI analyzing song title & artist...")
        filename = os.path.basename(saved_path)
        raw_title = info.get("title", os.path.splitext(filename)[0]) if info else os.path.splitext(filename)[0]
        raw_uploader = (info.get("uploader") or info.get("channel") or "") if info else ""
        raw_artist = (info.get("artist") or raw_uploader) if info else ""
        duration = float(info.get("duration", 0.0)) if info else 0.0

        # Auto-extract clean Song Title and clean Singer / Artist via Gemini AI + Rule-based fallback
        clean_title, clean_artist = clean_youtube_title_and_artist(raw_title, uploader=raw_uploader, raw_artist=raw_artist, use_gemini=True)
        print(f"[KMVM YouTube] Metadata resolved: Title='{clean_title}', Artist='{clean_artist}'")

        # Automatically rename downloaded audio and accompanying subtitle files to clean Song Title - Artist
        safe_fn = build_safe_audio_filename(clean_title, clean_artist, ext=os.path.splitext(saved_path)[1] or ".mp3")
        target_dir = os.path.dirname(saved_path)
        new_saved_path = os.path.join(target_dir, safe_fn)
        old_stem = os.path.splitext(filename)[0]
        new_stem = os.path.splitext(safe_fn)[0]

        if os.path.abspath(saved_path) != os.path.abspath(new_saved_path):
            try:
                if os.path.exists(new_saved_path):
                    try:
                        os.remove(new_saved_path)
                    except Exception as rm_err:
                        print(f"[KMVM YouTube] Existing target note: {rm_err}")
                os.rename(saved_path, new_saved_path)
                print(f"[KMVM YouTube] ✓ Renamed audio to authentic title: '{filename}' -> '{safe_fn}'")
                saved_path = new_saved_path
                filename = safe_fn

                # Concurrently rename any subtitle files sharing old_stem (e.g. .km.vtt, .en.vtt, .lrc, .srt)
                for f_item in os.listdir(target_dir):
                    if f_item.startswith(old_stem + ".") and f_item != safe_fn:
                        suffix = f_item[len(old_stem):]
                        old_sub_file = os.path.join(target_dir, f_item)
                        new_sub_file = os.path.join(target_dir, f"{new_stem}{suffix}")
                        try:
                            if os.path.exists(new_sub_file):
                                os.remove(new_sub_file)
                            os.rename(old_sub_file, new_sub_file)
                            print(f"[KMVM YouTube] ✓ Renamed subtitle: '{f_item}' -> '{os.path.basename(new_sub_file)}'")
                        except Exception as sub_ren_err:
                            print(f"[KMVM YouTube] Subtitle rename note: {sub_ren_err}")
            except Exception as ren_err:
                print(f"[KMVM YouTube] Audio rename note: {ren_err}")

        update_youtube_progress(95, "🤖 Gemini AI retrieving synchronized lyrics...")
        # Auto-detect subtitles / lyrics downloaded with the video
        lyrics = None
        target_pref = "km" if is_khmer_text(raw_title + " " + clean_title) else None
        sub_path = find_matching_subtitles(saved_path, target_lang=target_pref)
        if sub_path and os.path.exists(sub_path):
            try:
                lyrics = parse_subtitle_file(sub_path)
                # Guard against YouTube's auto-generated non-Khmer (Thai, English) captions on Khmer songs
                if lyrics and is_khmer_text(raw_title + " " + clean_title):
                    sample_text = " ".join([l.get("text", "") for l in lyrics[:10]])
                    if not is_khmer_text(sample_text):
                        print(f"[KMVM Lyrics] ⚠️ Discarded non-Khmer auto-subtitles for Khmer song '{clean_title}': '{sample_text[:60]}'")
                        lyrics = None
                if lyrics:
                    print(f"[KMVM Lyrics] Automatically loaded subtitle for {filename}: {os.path.basename(sub_path)} ({len(lyrics)} lines)")
            except Exception as e:
                print(f"[KMVM Lyrics] Subtitle parse warning: {e}")

        # Fallback to authentic Khmer Lyric Matcher (Gemini Cloud AI / DB / Description)
        if not lyrics and is_khmer_text(raw_title + " " + clean_title):
            try:
                try:
                    from backend.khmer_lyric_matcher import match_or_fetch_khmer_lyrics
                except ImportError:
                    from khmer_lyric_matcher import match_or_fetch_khmer_lyrics
                desc = info.get("description", "") if info else ""
                matcher_res = match_or_fetch_khmer_lyrics(
                    audio_path=saved_path,
                    title=clean_title,
                    artist=clean_artist,
                    duration=duration,
                    description=desc
                )
                if matcher_res:
                    lrc_path, aligned = matcher_res
                    lyrics = parse_subtitle_file(lrc_path)
                    print(f"[Khmer Lyric Matcher] ✅ Auto-matched authentic lyrics for '{clean_title}': {len(lyrics)} lines")
            except Exception as match_err:
                print(f"[Khmer Lyric Matcher] Warning: {match_err}")

        # Fallback to LRCLIB verified synchronized lyrics for international songs
        if not lyrics:
            try:
                lrc_text = fetch_synced_lyrics_lrclib(clean_title, clean_artist)
                if lrc_text:
                    lrclib_lyrics = parse_subtitle_content(lrc_text)
                    if lrclib_lyrics and len(lrclib_lyrics) >= 4:
                        lyrics = lrclib_lyrics
                        base_audio = os.path.splitext(saved_path)[0]
                        with open(f"{base_audio}.lrc", "w", encoding="utf-8") as f:
                            f.write(lrc_text)
                        print(f"[LRCLIB Auto-Match] ✅ Auto-matched {len(lyrics)} lines for '{clean_title}'!")
            except Exception as lrc_err:
                print(f"[LRCLIB Auto-Match] Notice: {lrc_err}")

        encoded_filename = urllib.parse.quote(filename)

        update_youtube_progress(100, f"Ready: {clean_title}")

        return {
            "status": "success",
            "audio_path": saved_path,
            "audio_url": f"/uploads/audio/{encoded_filename}",
            "filename": filename,
            "title": clean_title,
            "artist": clean_artist,
            "duration": duration,
            "lyrics": lyrics,
            "has_lyrics": bool(lyrics)
        }
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"[KMVM FATAL ERROR] {err}", flush=True)
        update_youtube_progress(0, f"Processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}\n{err}")

@app.get("/api/youtube/progress")
def get_youtube_progress():
    """Returns real-time download and processing progress percentage for YouTube extraction."""
    return youtube_progress

@app.get("/api/youtube/auth/status")
def youtube_auth_status():
    """Returns connected YouTube channel details or connection status."""
    try:
        from backend.youtube_uploader import get_youtube_channel_info
        return get_youtube_channel_info()
    except Exception as e:
        return {"connected": False, "error": str(e)}

@app.post("/api/youtube/auth/connect")
def youtube_auth_connect():
    """Triggers browser authorization flow to connect YouTube channel."""
    try:
        from backend.youtube_uploader import trigger_browser_auth
        return trigger_browser_auth()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class YouTubePreviewRequest(BaseModel):
    song_title: Optional[str] = ""
    artist_name: Optional[str] = ""
    lyrics_data: Optional[List[Dict[str, Any]]] = None
    theme: Optional[str] = "trap_circle"
    aspect_ratio: Optional[str] = "16:9"

@app.post("/api/youtube/preview_metadata")
def preview_youtube_metadata_api(req: YouTubePreviewRequest):
    """Generates preview of viral YouTube title, description with lyrics, and tags."""
    from backend.youtube_uploader import build_youtube_metadata
    return build_youtube_metadata(
        song_title=req.song_title,
        artist_name=req.artist_name,
        lyrics_data=req.lyrics_data,
        theme=req.theme,
        aspect_ratio=req.aspect_ratio
    )

@app.get("/api/youtube/config")
def get_youtube_config_api():
    """Returns the standard YouTube default metadata JSON configuration."""
    from backend.youtube_uploader import load_youtube_defaults
    return load_youtube_defaults()

@app.post("/api/youtube/config")
def update_youtube_config_api(data: Dict[str, Any]):
    """Saves updated YouTube default metadata JSON configuration."""
    from backend.youtube_uploader import save_youtube_defaults
    success = save_youtube_defaults(data)
    return {"status": "success" if success else "error"}

@app.post("/api/analyze")
def analyze_audio_structure(req: AnalyzeRequest):
    """Deep acoustic feature extraction, sections, viral hook, and waveform envelope."""
    if not os.path.exists(req.audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    try:
        engine = _get_AISongUnderstandingEngine()(req.audio_path)
        features = engine.analyze_audio_features()
        sections_objs = engine.detect_song_sections(features)
        
        sections = []
        best_hook = None
        for s in sections_objs:
            sec_dict = {
                "name": s.name,
                "start": round(float(s.start), 2),
                "end": round(float(s.end), 2),
                "duration": round(float(s.duration), 2),
                "energy": round(float(s.energy), 2),
                "is_best": bool(s.is_best_part),
                "score": round(float(s.score), 1)
            }
            sections.append(sec_dict)
            if s.is_best_part and best_hook is None:
                best_hook = sec_dict
        
        if not best_hook and sections:
            sorted_sec = sorted(sections, key=lambda x: x.get("energy", 0), reverse=True)
            best_hook = sorted_sec[0]
            best_hook["is_best"] = True

        # Compute waveform envelope peaks (600 - 1200 points)
        audio_data = engine.audio_data
        n_peaks = 600
        step = max(1, len(audio_data) // n_peaks)
        peaks = []
        for i in range(0, min(len(audio_data), n_peaks * step), step):
            chunk = audio_data[i:i + step]
            amp = float(np.max(np.abs(chunk))) if len(chunk) > 0 else 0.0
            peaks.append(round(min(1.0, amp * 1.3), 3))

        # Estimate musical key
        detected_key = "C Minor"
        try:
            import librosa
            chroma = librosa.feature.chroma_cqt(y=audio_data, sr=engine.sr)
            chroma_vals = np.mean(chroma, axis=1)
            notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
            tonic_idx = int(np.argmax(chroma_vals))
            third_minor = chroma_vals[(tonic_idx + 3) % 12]
            third_major = chroma_vals[(tonic_idx + 4) % 12]
            mode = "Minor" if third_minor > third_major else "Major"
            detected_key = f"{notes[tonic_idx]} {mode}"
        except Exception:
            pass

        return {
            "status": "success",
            "bpm": int(features.get("bpm", 120)),
            "key": detected_key,
            "energy": round(float(features.get("energy", 0.78)), 2),
            "mood": features.get("mood", "Energetic"),
            "genre": features.get("genre", "Modern Electronic"),
            "duration": round(float(engine.duration), 2),
            "hook": best_hook,
            "sections": sections,
            "waveform_peaks": peaks
        }
    except Exception as e:
        print(f"Analyze error: {e}")
        return {
            "status": "fallback",
            "bpm": 128,
            "energy": 0.82,
            "mood": "Dynamic",
            "genre": "Synth / Dance",
            "duration": 14.0,
            "hook": {"name": "CHORUS (⭐ VIRAL HOOK)", "start": 2.0, "end": 8.0, "score": 96.5, "is_best": True},
            "sections": [
                {"name": "INTRO", "start": 0.0, "end": 2.0, "energy": 0.4, "is_best": False, "score": 60.0},
                {"name": "CHORUS (⭐ VIRAL HOOK)", "start": 2.0, "end": 8.0, "energy": 0.95, "is_best": True, "score": 96.5},
                {"name": "VERSE", "start": 8.0, "end": 12.0, "energy": 0.7, "is_best": False, "score": 75.0},
                {"name": "OUTRO", "start": 12.0, "end": 14.0, "energy": 0.5, "is_best": False, "score": 65.0}
            ],
            "waveform_peaks": [float(abs(np.sin(i * 0.1) * 0.7 + 0.2)) for i in range(300)]
        }

@app.post("/api/ai/llm/analyze")
def llm_analyze_text(req: LLMAnalyzeRequest):
    """Uses Gemini / local model to analyze Khmer text for semantic meaning or auto-align with loaded lyrics."""
    try:
        # Check if user has lyrics loaded in teleprompter and pasted lyric lines to align/correct
        if req.lyrics_data and len(req.lyrics_data) > 0 and req.text and any('\u1780' <= c <= '\u17FF' for c in req.text):
            lines = [l.strip() for l in req.text.splitlines() if l.strip()]
            if len(lines) >= 3 or any(w in req.text for w in ["កែ", "align", "lyrics", "ទំនុកច្រៀង", "កែអត្ថបទ", "តម្រឹម"]):
                from backend.llm_engine import align_and_correct_lyrics_with_reference
                corrected_lyrics, report = align_and_correct_lyrics_with_reference(req.lyrics_data, req.text)
                return {
                    "status": "success",
                    "aligned": True,
                    "analysis": f"⚡ **Gemini Aligned Lyrics**: Successfully matched & corrected {report.get('changes_count', 0)} lines with your original text, preserving all audio timestamps!",
                    "changes_count": report.get("changes_count", 0),
                    "lyrics": corrected_lyrics,
                    "report": report
                }
        result = llm_engine.analyze_khmer_text(req.text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Analysis failed: {str(e)}")

@app.post("/api/ai/llm/translate")
def llm_translate_text(req: LLMTranslateRequest):
    """Translates English to Khmer using the local model."""
    try:
        result = llm_engine.translate_to_khmer(req.text)
        return {"status": "success", "translation": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Translation failed: {str(e)}")

@app.post("/api/ai/chat/clear")
def clear_ai_chat_history():
    """Clears conversation memory so the AI starts fresh (e.g. after loading a new song)."""
    try:
        llm_engine.clear_history()
        return {"status": "success", "message": "AI conversation memory cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear chat history: {str(e)}")

@app.post("/api/lyrics/generate")
def generate_lyrics_api(req: GenerateLyricsRequest):
    """Generates structured, poetic Khmer lyrics with rhyming verse patterns and synchronized LRC output."""
    try:
        result = llm_engine.generate_khmer_lyrics(prompt=req.prompt or "", genre=req.genre or "romantic", bpm=req.bpm or 85)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lyrics generation failed: {str(e)}")

@app.post("/api/lyrics/polish")
def polish_lyrics_api(req: PolishLyricsRequest):
    """Normalizes and fixes spelling and subscript issues in Khmer lyrics."""
    try:
        result = llm_engine.polish_khmer_lyrics(raw_lyrics=req.lyrics_text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lyrics polishing failed: {str(e)}")

@app.post("/api/thumbnail")
def generate_thumbnail_concepts(req: ThumbnailRequest):
    """Generates 3 distinct high-CTR thumbnail cards."""
    try:
        thumb_dir = os.path.join(OUTPUT_DIR, "thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)
        gen = _get_ThumbnailGenerator()(req.song_title, req.artist_name, req.background_image)
        concepts = gen.generate_concepts(thumb_dir)
        urls = [f"/outputs/thumbnails/{os.path.basename(c)}" for c in concepts]
        return {
            "status": "success",
            "thumbnails": urls,
            "count": len(urls)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Thumbnail generation error: {str(e)}")

def _execute_render_job(job_id: str, req: RenderRequest):
    """Worker function executed in background thread."""
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["percent"] = 1.0

        # Determine resolution (1080p, 720p, 480p)
        res_choice = (getattr(req, "resolution", "1080p") or "1080p").lower()
        if req.aspect_ratio == "9:16":
            if "720" in res_choice:
                width, height = 720, 1280
            elif "480" in res_choice:
                width, height = 480, 854
            else:
                width, height = 1080, 1920
        else:
            if "720" in res_choice:
                width, height = 1280, 720
            elif "480" in res_choice:
                width, height = 854, 480
            else:
                width, height = 1920, 1080

        # Determine descriptive output filename incorporating song title and artist
        candidate_title = (req.song_title or "").strip()
        candidate_artist = (req.artist_name or "").strip()
        if candidate_artist in ("Official Audio", "Unknown", "Artist", "None", ""):
            candidate_artist = ""

        if candidate_title and candidate_artist:
            base_display_name = f"{candidate_artist} - {candidate_title}"
        elif candidate_title:
            base_display_name = candidate_title
        elif req.audio_path:
            base_display_name = os.path.splitext(os.path.basename(req.audio_path))[0]
        else:
            base_display_name = f"VIDA_Visualizer_{job_id[:8]}"

        # Sanitize for Windows filesystem characters: \ / : * ? " < > |
        safe_name = re.sub(r'[\\/*?:"<>|]', "", base_display_name).strip()
        safe_name = re.sub(r'\s+', ' ', safe_name)
        if not safe_name:
            safe_name = f"VIDA_Visualizer_{job_id[:8]}"

        # Truncate to maximum 100 chars to guarantee MAX_PATH safety on Windows
        if len(safe_name) > 100:
            safe_name = safe_name[:100].strip()

        # Check for filename collisions in OUTPUT_DIR
        target_candidate = f"{safe_name}.mp4"
        if os.path.exists(os.path.join(OUTPUT_DIR, target_candidate)):
            output_filename = f"{safe_name} ({job_id[:6]}).mp4"
        else:
            output_filename = target_candidate

        output_path = os.path.join(OUTPUT_DIR, output_filename)

        def on_progress(p_data):
            jobs[job_id].update({
                "percent": p_data["percent"],
                "frame": p_data["frame"],
                "total_frames": p_data["total_frames"],
                "fps": p_data["fps"],
                "eta_seconds": p_data["eta_seconds"]
            })

        # Ensure we always prioritize verified authentic synced lyrics if available on disk
        render_lyrics = req.lyrics_data or []
        if req.audio_path and os.path.exists(req.audio_path):
            base_audio, _ = os.path.splitext(req.audio_path)
            cand_lrcs = [
                f"{base_audio}.vi.lrc",
                f"{base_audio}.km.lrc",
                f"{base_audio}.lrc",
                req.audio_path.replace(".mp3", ".vi.lrc").replace(".wav", ".vi.lrc"),
                req.audio_path.replace(".mp3", ".lrc").replace(".wav", ".lrc")
            ]
            for cand in cand_lrcs:
                if os.path.exists(cand):
                    try:
                        disk_lyrics = parse_subtitle_file(cand, audio_path=req.audio_path)
                        if disk_lyrics and len(disk_lyrics) >= 4:
                            print(f"[Render Engine] 🎯 Auto-loaded verified authentic lyrics ({len(disk_lyrics)} lines) from {os.path.basename(cand)}")
                            render_lyrics = disk_lyrics
                            break
                    except Exception as lrc_err:
                        print(f"[Render Engine] Warning reading {cand}: {lrc_err}")

        VideoRenderer = _get_VideoRenderer()
        # Second (translated) lyric track — display-only cue copy, originals untouched
        display_mode = (req.display_mode or "original_only").strip().lower()
        display_lyrics = build_translation_display_lyrics(render_lyrics, display_mode, req.translation_lines)
        if display_mode == "translation_only" and display_lyrics is not render_lyrics:
            print(f"[Render Engine] 🌐 Display mode = translation_only ({len(req.translation_lines or [])} translated lines)")
        elif display_mode == "bilingual":
            print(f"[Render Engine] 🌐 Display mode = bilingual (original + translated subline)")
        renderer = VideoRenderer(
            audio_path=req.audio_path,
            output_path=output_path,
            width=width,
            height=height,
            fps=req.fps,
            theme=req.theme,
            palette_name=req.palette,
            background_image=req.background_image,
            logo_image=req.logo_image,
            center_text_primary=req.center_text_primary,
            center_text_secondary=req.center_text_secondary,
            show_center_text=req.show_center_text if req.show_center_text is not None else True,
            song_title=req.song_title,
            artist_name=req.artist_name,
            title_scale=req.title_scale,
            lyrics_data=display_lyrics,
            lyric_style=req.lyric_style,
            bar_count=req.bar_count,
            bass_boost=req.bass_boost,
            display_mode=display_mode,
            translation_lines=req.translation_lines or [],
            translation_lang=req.translation_lang or "en",
            translation_style=req.translation_style or {}
        )

        renderer.render_video(progress_callback=on_progress)

        youtube_url = None
        if req.auto_post_youtube:
            try:
                jobs[job_id]["status"] = "uploading"
                jobs[job_id]["upload_percent"] = 0
                jobs[job_id]["message"] = "Uploading to YouTube (0%)..."

                def on_yt_progress(pct: int):
                    jobs[job_id]["upload_percent"] = pct
                    jobs[job_id]["message"] = f"Uploading to YouTube ({pct}%)..."

                # Local import to prevent breaking app startup if credentials missing
                from backend.youtube_uploader import upload_video_to_youtube, build_youtube_metadata
                
                meta = build_youtube_metadata(
                    song_title=req.song_title,
                    artist_name=req.artist_name,
                    lyrics_data=req.lyrics_data,
                    theme=req.theme,
                    aspect_ratio=req.aspect_ratio,
                    custom_title=req.youtube_title,
                    custom_desc=req.youtube_description,
                    custom_tags=req.youtube_tags
                )
                privacy = req.youtube_privacy if req.youtube_privacy in ("public", "unlisted", "private") else "public"

                youtube_url = upload_video_to_youtube(
                    video_path=output_path,
                    title=meta["title"],
                    description=meta["description"],
                    tags=meta["tags"],
                    privacy_status=privacy,
                    progress_callback=on_yt_progress
                )
            except Exception as yt_err:
                print(f"[YouTube Upload Error] {yt_err}")
                jobs[job_id]["youtube_error"] = str(yt_err)

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["percent"] = 100.0
        jobs[job_id]["output_url"] = f"/outputs/{urllib.parse.quote(output_filename)}"
        jobs[job_id]["output_filename"] = output_filename
        jobs[job_id]["output_path"] = output_path
        jobs[job_id]["youtube_url"] = youtube_url

    except Exception as e:
        import traceback
        traceback.print_exc()
        err_msg = str(e) or repr(e) or type(e).__name__
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = err_msg
        print(f"Rendering error for job {job_id}: {err_msg}")

@app.post("/api/render")
async def start_render(req: RenderRequest, background_tasks: BackgroundTasks):
    """Starts video render job and returns job ID."""
    if not os.path.exists(req.audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    job_id = uuid.uuid4().hex
    jobs[job_id] = {
        "status": "queued",
        "percent": 0.0,
        "fps": 0.0,
        "eta_seconds": 0.0,
        "output_url": None,
        "error": None
    }

    # Run in separate thread to prevent blocking event loop
    thread = threading.Thread(target=_execute_render_job, args=(job_id, req))
    thread.daemon = True
    thread.start()

    return {"job_id": job_id, "status": "started"}

@app.get("/api/progress/{job_id}")
async def get_progress(job_id: str):
    """Polls progress of an active render job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.post("/api/export/mux")
async def export_mux_api(video: UploadFile = File(...), audio_path: str = Form(""), container: str = Form("mp4")):
    """
    WYSIWYG export finisher: the browser encodes the exact preview frames (WebCodecs) and posts
    the silent video here. We stream-copy it and mux the original audio in seconds (no re-encode
    of the video), so what you saw in the studio is bit-for-bit what you get.
    """
    exports_dir = os.path.join(OUTPUT_DIR, "exports")
    os.makedirs(exports_dir, exist_ok=True)
    stamp = _time.strftime("%Y%m%d_%H%M%S")

    is_mp4 = (video.filename or "v.mp4").lower().endswith(".mp4") and container != "webm"
    vpath = os.path.join(exports_dir, f"client_video_{stamp}{'.mp4' if is_mp4 else '.webm'}")
    with open(vpath, "wb") as vf:
        while chunk := await video.read(1024 * 1024):
            vf.write(chunk)

    audio_p = audio_path or ""
    if audio_p:
        clean_rel = audio_p.replace("\\", "/").lstrip("/")
        candidates = [
            audio_p,
            os.path.abspath(audio_p),
            os.path.join(AUDIO_DIR, os.path.basename(audio_p)),
            os.path.join(UPLOAD_DIR, "audio", os.path.basename(audio_p)),
            os.path.join(os.path.dirname(AUDIO_DIR), clean_rel),
        ]
        audio_p = next((c for c in candidates if c and os.path.exists(c)), None)

    if not audio_p:
        return {
            "status": "success",
            "path": vpath,
            "url": f"/outputs/exports/{os.path.basename(vpath)}",
            "muxed": False,
            "detail": "No audio path supplied; silent video returned",
        }

    out_path = os.path.join(
        exports_dir,
        f"{os.path.splitext(os.path.basename(audio_p))[0]}_vida_{stamp}.mp4"
    )
    ffmpeg_bin = get_ffmpeg_binary()
    if is_mp4:
        # Stream-copy the browser-encoded video, transcode audio only (fast)
        cmd = [
            ffmpeg_bin, "-y", "-i", vpath, "-i", audio_p,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", out_path,
        ]
    else:
        cmd = [
            ffmpeg_bin, "-y", "-i", vpath,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", out_path,
        ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(out_path):
        raise HTTPException(status_code=500, detail=f"Audio mux failed: {proc.stderr[-800:]}")
    try:
        os.remove(vpath)
    except OSError:
        pass
    return {
        "status": "success",
        "path": out_path,
        "url": f"/outputs/exports/{os.path.basename(out_path)}",
        "muxed": True,
    }


class ExportPostYouTubeRequest(BaseModel):
    video_path: str
    song_title: Optional[str] = ""
    artist_name: Optional[str] = ""
    theme: Optional[str] = "trap_circle"
    aspect_ratio: Optional[str] = "16:9"
    privacy: Optional[str] = "public"
    youtube_title: Optional[str] = None
    youtube_description: Optional[str] = None


@app.post("/api/export/post-youtube")
async def export_post_youtube(req: ExportPostYouTubeRequest):
    """Uploads a client-exported (WYSIWYG) video to YouTube with the same metadata builder."""
    if not os.path.exists(req.video_path):
        raise HTTPException(status_code=404, detail="Exported video not found")
    try:
        from backend.youtube_uploader import upload_video_to_youtube, build_youtube_metadata
        meta = build_youtube_metadata(
            song_title=req.song_title,
            artist_name=req.artist_name,
            lyrics_data=None,
            theme=req.theme,
            aspect_ratio=req.aspect_ratio,
            custom_title=req.youtube_title,
            custom_desc=req.youtube_description,
        )
        privacy = req.privacy if req.privacy in ("public", "unlisted", "private") else "public"
        url = upload_video_to_youtube(
            video_path=req.video_path,
            title=meta["title"],
            description=meta["description"],
            tags=meta["tags"],
            privacy_status=privacy,
        )
        return {"status": "success", "youtube_url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"YouTube upload failed: {str(e)}")

@app.get("/api/demo")
async def get_demo_assets():
    """Generates and returns ready-to-test demo track with synced lyrics."""
    demo_audio_path = os.path.join(AUDIO_DIR, "demo_synthwave.wav")
    if not os.path.exists(demo_audio_path):
        _get_demo_audio().generate_demo_track(demo_audio_path, duration_sec=14.0)

    demo_lyrics = [
        {
            "line_id": 0,
            "start": 0.5,
            "end": 3.8,
            "text": "Feel the electric pulse in the night",
            "words": [
                {"word": "Feel", "start": 0.5, "end": 1.1},
                {"word": "the", "start": 1.1, "end": 1.5},
                {"word": "electric", "start": 1.5, "end": 2.3},
                {"word": "pulse", "start": 2.3, "end": 3.0},
                {"word": "in", "start": 3.0, "end": 3.3},
                {"word": "the", "start": 3.3, "end": 3.5},
                {"word": "night", "start": 3.5, "end": 3.8}
            ]
        },
        {
            "line_id": 1,
            "start": 4.2,
            "end": 7.5,
            "text": "Cyber city glowing neon light",
            "words": [
                {"word": "Cyber", "start": 4.2, "end": 4.9},
                {"word": "city", "start": 4.9, "end": 5.5},
                {"word": "glowing", "start": 5.5, "end": 6.3},
                {"word": "neon", "start": 6.3, "end": 6.9},
                {"word": "light", "start": 6.9, "end": 7.5}
            ]
        },
        {
            "line_id": 2,
            "start": 8.0,
            "end": 11.2,
            "text": "Bass is dropping let the sound ignite",
            "words": [
                {"word": "Bass", "start": 8.0, "end": 8.6},
                {"word": "is", "start": 8.6, "end": 8.9},
                {"word": "dropping", "start": 8.9, "end": 9.7},
                {"word": "let", "start": 9.7, "end": 10.0},
                {"word": "the", "start": 10.0, "end": 10.3},
                {"word": "sound", "start": 10.3, "end": 10.8},
                {"word": "ignite", "start": 10.8, "end": 11.2}
            ]
        },
        {
            "line_id": 3,
            "start": 11.6,
            "end": 13.8,
            "text": "VIDA visualizer shining bright",
            "words": [
                {"word": "VIDA", "start": 11.6, "end": 12.2},
                {"word": "visualizer", "start": 12.2, "end": 13.0},
                {"word": "shining", "start": 13.0, "end": 13.4},
                {"word": "bright", "start": 13.4, "end": 13.8}
            ]
        }
    ]
    demo_lyrics, _ = double_check_lyrics(demo_lyrics)

    return {
        "audio_path": demo_audio_path,
        "audio_url": "/uploads/audio/demo_synthwave.wav",
        "title": "Cyber Horizon",
        "artist": "VIDA Synth Engine",
        "lyrics": demo_lyrics,
        "lyrics_verified": True,
        "bpm": 128,
        "energy": 0.85,
        "mood": "Cyberpunk Synthwave",
        "genre": "Retrowave / Trap",
        "duration": 14.0,
        "hook": {
            "name": "CHORUS (⭐ VIRAL HOOK)",
            "start": 4.2,
            "end": 11.2,
            "score": 98.2,
            "is_best": True
        },
        "sections": [
            {"name": "INTRO", "start": 0.0, "end": 4.2, "energy": 0.45, "is_best": False, "score": 65.0},
            {"name": "CHORUS (⭐ VIRAL HOOK)", "start": 4.2, "end": 11.2, "energy": 0.95, "is_best": True, "score": 98.2},
            {"name": "OUTRO", "start": 11.2, "end": 14.0, "energy": 0.60, "is_best": False, "score": 70.0}
        ]
    }


@app.get("/api/demo/sinisamut")
async def get_sinisamut_demo():
    """Generates and returns ready-to-test Sinn Sisamouth 60s golden era demo track with synced Khmer lyrics."""
    demo_audio_path = os.path.join(AUDIO_DIR, "demo_sinisamut.wav")
    if not os.path.exists(demo_audio_path):
        _get_demo_audio().generate_khmer_60s_demo(demo_audio_path, duration_sec=18.0)

    sinisamut_lyrics = [
        {
            "line_id": 0,
            "start": 0.8,
            "end": 4.5,
            "text": "ឱ! ដួងចំប៉ា... ចំប៉ាបាត់ដំបង",
            "words": [
                {"word": "ឱ!", "start": 0.8, "end": 1.4},
                {"word": "ដួង", "start": 1.4, "end": 1.9},
                {"word": "ចំប៉ា...", "start": 1.9, "end": 2.8},
                {"word": "ចំប៉ា", "start": 2.8, "end": 3.4},
                {"word": "បាត់ដំបង", "start": 3.4, "end": 4.5}
            ]
        },
        {
            "line_id": 1,
            "start": 5.0,
            "end": 8.8,
            "text": "ក្លិនក្រអូបផ្សង... ឆ្ងាយឆ្លងកាត់ស្ទឹងសង្កែ",
            "words": [
                {"word": "ក្លិន", "start": 5.0, "end": 5.5},
                {"word": "ក្រអូប", "start": 5.5, "end": 6.2},
                {"word": "ផ្សង...", "start": 6.2, "end": 6.9},
                {"word": "ឆ្ងាយ", "start": 6.9, "end": 7.4},
                {"word": "ឆ្លងកាត់", "start": 7.4, "end": 8.0},
                {"word": "ស្ទឹងសង្កែ", "start": 8.0, "end": 8.8}
            ]
        },
        {
            "line_id": 2,
            "start": 9.2,
            "end": 13.0,
            "text": "រៀមនឹកស្រណោះ... សម្រស់មាសមេ",
            "words": [
                {"word": "រៀម", "start": 9.2, "end": 9.7},
                {"word": "នឹក", "start": 9.7, "end": 10.2},
                {"word": "ស្រណោះ...", "start": 10.2, "end": 11.2},
                {"word": "សម្រស់", "start": 11.2, "end": 12.0},
                {"word": "មាសមេ", "start": 12.0, "end": 13.0}
            ]
        },
        {
            "line_id": 3,
            "start": 13.5,
            "end": 17.5,
            "text": "ធ្លាប់ថ្នមបំពេ... ក្រោមម្លប់ចំប៉ា...",
            "words": [
                {"word": "ធ្លាប់", "start": 13.5, "end": 14.1},
                {"word": "ថ្នម", "start": 14.1, "end": 14.8},
                {"word": "បំពេ...", "start": 14.8, "end": 15.8},
                {"word": "ក្រោម", "start": 15.8, "end": 16.4},
                {"word": "ម្លប់ចំប៉ា...", "start": 16.4, "end": 17.5}
            ]
        }
    ]
    sinisamut_lyrics, _ = double_check_lyrics(sinisamut_lyrics)

    return {
        "audio_path": demo_audio_path,
        "audio_url": "/uploads/audio/demo_sinisamut.wav",
        "title": "ចំប៉ាបាត់ដំបង (Champa Battambang)",
        "artist": "ស៊ីន ស៊ីសាមុត (Sinn Sisamouth)",
        "lyrics": sinisamut_lyrics,
        "lyrics_verified": True,
        "template": "vinyl_60s",
        "theme": "trap_circle",
        "palette": "vintage_vinyl",
        "lyric_style": "typewriter",
        "bpm": 86,
        "energy": 0.62,
        "mood": "Nostalgic 1960s Cambodian Golden Era",
        "genre": "Classic Khmer Ballad / Rumba",
        "duration": 18.0,
        "hook": {
            "name": "CHORUS (👑 យុគមាស 60s)",
            "start": 0.8,
            "end": 8.8,
            "score": 99.5,
            "is_best": True
        },
        "sections": [
            {"name": "INTRO", "start": 0.0, "end": 0.8, "energy": 0.40, "is_best": False, "score": 60.0},
            {"name": "CHORUS (👑 យុគមាស 60s)", "start": 0.8, "end": 8.8, "energy": 0.68, "is_best": True, "score": 99.5},
            {"name": "VERSE", "start": 8.8, "end": 17.5, "energy": 0.65, "is_best": False, "score": 75.0}
        ]
    }


# Static Mounts
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

if os.path.exists(os.path.join(FRONTEND_DIR, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="frontend_assets")

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend_static")

@app.get("/")
async def serve_index():
    """Serves the studio frontend UI."""
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "VIDA Backend Ready. Frontend loading..."}

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

@app.get("/favicon.svg")
async def favicon_svg():
    path = os.path.join(FRONTEND_DIR, "favicon.svg")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/svg+xml")
    return Response(status_code=204)

@app.get("/icons.svg")
async def icons_svg():
    path = os.path.join(FRONTEND_DIR, "icons.svg")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/svg+xml")
    return Response(status_code=204)

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_config():
    return Response(content="{}", media_type="application/json", status_code=200)

@app.get("/api/dev/mtime")
async def get_frontend_mtime():
    """Returns the max modification time of all files in frontend directory for auto-reloading."""
    max_mtime = 0
    for root, _, files in os.walk(FRONTEND_DIR):
        for file in files:
            try:
                mtime = os.path.getmtime(os.path.join(root, file))
                if mtime > max_mtime:
                    max_mtime = mtime
            except OSError:
                pass
    return {"mtime": max_mtime}
