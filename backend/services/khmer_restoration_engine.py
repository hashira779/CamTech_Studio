"""
Khmer Oldies AI Restoration Studio — Core DSP & AI Engine
Engineered specifically for vintage Cambodian recordings (1950s–1990s).

Preserves original singer identity, vocal character, traditional instruments,
and historical recording acoustics while removing rumble, hiss, hum, and boxy tape resonance.
"""

import json
import logging
import math
import os
import subprocess
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    from backend.paths import UPLOAD_DIR
    from backend.services import restoration_db
except ImportError:
    from paths import UPLOAD_DIR
    from services import restoration_db

log = logging.getLogger("backend.restoration_engine")

RESTORE_DIR = os.path.join(UPLOAD_DIR, "restored")
STEMS_DIR = os.path.join(UPLOAD_DIR, "stems")
TIMEOUT_S = 1800

# ---------------------------------------------------------------------------
# 5 Restoration Presets
# ---------------------------------------------------------------------------

PRESETS: Dict[str, Dict[str, Any]] = {
    "archival_preservation": {
        "id": "archival_preservation",
        "name": "Archival Preservation",
        "description": "Museum & collector grade. Minimal processing. Preserves full vintage dynamic range and acoustic atmosphere.",
        "hiss_reduction_db": 8,
        "hiss_noise_floor_db": -42,
        "rumble_cutoff_hz": 35,
        "hum_removal": True,
        "declick": False,
        "warmth_db": 0.0,
        "demud_db": 0.0,
        "vocal_presence_db": 0.0,
        "air_sparkle_db": 0.0,
        "stereo_widening": False,
        "target_lufs": None,  # Preserves original dynamics
        "use_demucs": False,
    },
    "gentle_cleanup": {
        "id": "gentle_cleanup",
        "name": "Gentle Cleanup",
        "description": "Removes moderate tape hiss, rumble, and vinyl crackle while maintaining 100% of the original tonal balance.",
        "hiss_reduction_db": 12,
        "hiss_noise_floor_db": -38,
        "rumble_cutoff_hz": 45,
        "hum_removal": True,
        "declick": True,
        "warmth_db": 0.8,
        "demud_db": -1.2,
        "vocal_presence_db": 1.5,
        "air_sparkle_db": 0.0,
        "stereo_widening": False,
        "target_lufs": -16.0,
        "use_demucs": False,
    },
    "vintage_studio": {
        "id": "vintage_studio",
        "name": "Vintage Studio",
        "description": "Golden Era analog tape warmth. Cleans mud, lifts vocal presence, and restores warmth as heard in the original studio room.",
        "hiss_reduction_db": 15,
        "hiss_noise_floor_db": -34,
        "rumble_cutoff_hz": 50,
        "hum_removal": True,
        "declick": True,
        "warmth_db": 1.5,
        "demud_db": -2.0,
        "vocal_presence_db": 2.8,
        "air_sparkle_db": 1.5,
        "stereo_widening": False,
        "target_lufs": -14.0,
        "use_demucs": False,
    },
    "advanced_ai": {
        "id": "advanced_ai",
        "name": "Advanced AI Restoration",
        "description": "Demucs AI stem separation. Independent vocal and accompaniment mastering, subtle stereo soundstage, and vocal pocketing.",
        "hiss_reduction_db": 16,
        "hiss_noise_floor_db": -32,
        "rumble_cutoff_hz": 55,
        "hum_removal": True,
        "declick": True,
        "warmth_db": 1.2,
        "demud_db": -2.2,
        "vocal_presence_db": 3.2,
        "air_sparkle_db": 2.0,
        "stereo_widening": True,
        "target_lufs": -14.0,
        "use_demucs": True,
    },
    "modern_broadcast": {
        "id": "modern_broadcast",
        "name": "Modern Broadcast & Vocal Focus",
        "description": "Maximum clarity for YouTube, TikTok, and phone speakers. Strong de-hiss, vocal brought forward, and true-peak broadcast limiter.",
        "hiss_reduction_db": 20,
        "hiss_noise_floor_db": -28,
        "rumble_cutoff_hz": 65,
        "hum_removal": True,
        "declick": True,
        "warmth_db": 1.5,
        "demud_db": -2.5,
        "vocal_presence_db": 4.0,
        "air_sparkle_db": 2.5,
        "stereo_widening": True,
        "target_lufs": -14.0,
        "use_demucs": True,
    },
}

EXPORT_FORMATS = {
    "wav16": {"ext": "wav", "args": ["-c:a", "pcm_s16le"]},
    "wav24": {"ext": "wav", "args": ["-c:a", "pcm_s24le"]},
    "wav32": {"ext": "wav", "args": ["-c:a", "pcm_f32le"]},
    "mp3_320": {"ext": "mp3", "args": ["-c:a", "libmp3lame", "-b:a", "320k"]},
    "flac": {"ext": "flac", "args": ["-c:a", "flac"]},
}


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


# ---------------------------------------------------------------------------
# Stage 1: Audio Analysis
# ---------------------------------------------------------------------------

def analyze_audio_file(audio_path: str, max_samples_waveform: int = 300) -> Dict[str, Any]:
    """Inspects audio characteristics, dynamic loudness, defects, and waveform."""
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    try:
        from backend.audio_analyzer import decode_audio_to_numpy
    except ImportError:
        from audio_analyzer import decode_audio_to_numpy

    # 1. Decode audio to numpy array
    audio, sr, duration = decode_audio_to_numpy(audio_path, target_sr=22050)
    channels = 1 if audio.ndim == 1 else audio.shape[1]
    total_samples = len(audio)

    # Convert to mono for scalar analysis
    mono = audio if channels == 1 else audio.mean(axis=1)

    # 2. Peak & RMS
    peak = float(np.max(np.abs(mono))) + 1e-9
    peak_db = round(float(20 * np.log10(peak)), 2)

    rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2))) + 1e-9
    rms_db = round(float(20 * np.log10(rms)), 2)

    # 3. DC Offset & Digital Clipping
    dc_offset = round(float(np.mean(mono)), 5)
    clipping_samples = int(np.sum(np.abs(mono) >= 0.999))

    # 4. Noise Floor (10th percentile energy across 50 ms hops)
    hop = int(0.05 * sr)
    if hop > 0 and len(mono) >= hop:
        frames = mono[: len(mono) // hop * hop].reshape(-1, hop)
        frame_rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1)) + 1e-9
        db_frames = 20 * np.log10(frame_rms)
        noise_floor_db = round(float(np.percentile(db_frames, 10)), 1)
    else:
        noise_floor_db = -45.0

    # 5. Integrated Loudness (LUFS) via ffmpeg loudnorm
    lufs = _measure_lufs(audio_path)

    # 6. Downsampled Waveform Peaks for fast frontend rendering
    step = max(1, total_samples // max_samples_waveform)
    waveform = []
    for i in range(0, total_samples, step):
        chunk = mono[i : i + step]
        if len(chunk) > 0:
            val = float(np.max(np.abs(chunk)))
            waveform.append(round(val, 3))

    file_size = os.path.getsize(audio_path)

    return {
        "filename": os.path.basename(audio_path),
        "original_path": audio_path,
        "file_size_bytes": file_size,
        "duration_seconds": round(duration, 2),
        "sample_rate": sr,
        "channels": channels,
        "bit_depth": 16,  # default standard
        "peak_dbfs": peak_db,
        "rms_dbfs": rms_db,
        "loudness_lufs": lufs,
        "dc_offset": dc_offset,
        "clipping_samples": clipping_samples,
        "noise_floor_dbfs": noise_floor_db,
        "waveform_data": waveform,
    }


def _measure_lufs(audio_path: str) -> float:
    """Measures ITU-R BS.1770-4 Integrated Loudness using FFmpeg."""
    cmd = [
        _ffmpeg(), "-hide_banner", "-nostats", "-y", "-i", audio_path,
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
        "-f", "null", "-"
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=120)
        text = proc.stderr or ""
        start = text.rfind("{")
        if start != -1:
            m = json.loads(text[start : text.rfind("}") + 1])
            return round(float(m.get("input_i", -18.0)), 2)
    except Exception as e:
        log.warning(f"[Analysis] Could not measure LUFS: {e}")
    return -18.0


# ---------------------------------------------------------------------------
# Stages 2, 3 & 4: Cleanup, AI Restoration, and Vintage Archival Enhancement
# ---------------------------------------------------------------------------

def _build_filter_chains(params: Dict[str, Any], is_vocal_stem: bool = False, is_music_stem: bool = False) -> List[str]:
    """Generates FFmpeg filter chain for cleanup and vintage analog enhancement."""
    filters = []

    # Stage 2: Physics Cleanup
    # 1. Subsonic Rumble Cut
    hp = params.get("rumble_cutoff_hz", 45)
    if is_vocal_stem:
        hp = max(hp, 75)
    filters.append(f"highpass=f={hp}")

    # 2. De-Click & De-Crackle
    if params.get("declick", True):
        filters.append("adeclick")

    # 3. 50/60 Hz Mains Hum Notch Filter
    if params.get("hum_removal", True):
        filters.append("bandreject=f=50:w=3.0")
        filters.append("bandreject=f=100:w=3.0")
        filters.append("bandreject=f=60:w=3.0")
        filters.append("bandreject=f=120:w=3.0")

    # 4. Adaptive Spectral De-Hiss
    nr = params.get("hiss_reduction_db", 14)
    if is_vocal_stem:
        nr = max(4, nr - 6)  # Protect voice natural sibilance
    nf = params.get("hiss_noise_floor_db", -35)
    filters.append(f"afftdn=nr={nr}:nf={nf}")

    # Stage 4: Archival Vintage Enhancement
    # 5. Low-end Analog Warmth
    warmth = params.get("warmth_db", 1.0)
    if warmth > 0 and not is_vocal_stem:
        filters.append(f"equalizer=f=120:t=q:w=1.2:g={warmth:.1f}")

    # 6. De-Mudding Boxy Tape Resonance
    demud = params.get("demud_db", -1.5)
    if demud < 0:
        filters.append(f"equalizer=f=300:t=q:w=1.2:g={demud:.1f}")

    # 7. Khmer Vocal Formant Presence Lift (3.2–3.5 kHz)
    presence = params.get("vocal_presence_db", 2.0)
    if is_music_stem:
        # Carve acoustic pocket for vocal in the backing track
        filters.append("equalizer=f=3400:t=q:w=1.0:g=-2.0")
    elif presence > 0:
        filters.append(f"equalizer=f=3400:t=q:w=1.1:g={presence:.1f}")

    # 8. High-Air Sparkle
    air = params.get("air_sparkle_db", 1.5)
    if air > 0 and (is_vocal_stem or not is_music_stem):
        filters.append(f"equalizer=f=8200:t=q:w=1.4:g={air:.1f}")

    # 9. Stereo Soundstage Widening for Backing Band
    if is_music_stem and params.get("stereo_widening", False):
        filters.append("extrastereo=m=1.35")

    return filters


def restore_track(
    audio_path: str,
    preset_key: str = "vintage_studio",
    bypass_ai: bool = False,
    overrides: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Executes the full 5-stage restoration pipeline."""
    started = time.time()
    os.makedirs(RESTORE_DIR, exist_ok=True)

    if preset_key not in PRESETS:
        preset_key = "vintage_studio"

    params = dict(PRESETS[preset_key])
    if overrides:
        params.update(overrides)

    if job_id:
        restoration_db.update_job_status(job_id, "processing", 10.0)

    # Check for Demucs stems
    use_ai = params.get("use_demucs", False) and not bypass_ai
    stems = None

    if use_ai:
        stem_engine = params.get("stem_engine", "uvr_kim_vocal_2")
        try:
            if stem_engine.startswith("uvr_"):
                from backend import uvr_separator
                vocals_path, music_path = uvr_separator.separate_with_uvr(audio_path, engine_id=stem_engine)
                if os.path.isfile(vocals_path) and os.path.isfile(music_path):
                    stems = {"vocals": vocals_path, "music": music_path}
            else:
                from backend.vocal_align import get_cached_vocals_path, _ensure_vocal_stem
                vocals_path = get_cached_vocals_path(audio_path)
                if not vocals_path:
                    vocals_path = _ensure_vocal_stem(audio_path)
                if vocals_path:
                    music_path = vocals_path.replace("_vocals.wav", "_accompaniment.wav")
                    if os.path.isfile(music_path):
                        stems = {"vocals": vocals_path, "music": music_path}
        except Exception as e:
            log.warning(f"[Restoration] Stem separation with {stem_engine} failed, falling back: {e}")
            stems = None

    if job_id:
        restoration_db.update_job_status(job_id, "processing", 35.0)

    # Base name for output
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    out_name = f"{base_name} [restored {preset_key}].mp3"
    out_path = os.path.join(RESTORE_DIR, out_name)
    tmp_path = out_path + ".tmp.mp3"

    # Build FFmpeg command
    target_lufs = params.get("target_lufs")
    limiter = "alimiter=limit=0.89:attack=5:release=50:level=false"

    if stems:
        vocal_filters = ",".join(_build_filter_chains(params, is_vocal_stem=True) + ["volume=3.0dB"])
        music_filters = ",".join(_build_filter_chains(params, is_music_stem=True))
        graph = f"[0:a]{vocal_filters}[v];[1:a]{music_filters}[m];[v][m]amix=inputs=2:normalize=0"
        if params.get("air_sparkle_db", 0) > 1.0:
            graph += ",aexciter=amount=0.5:drive=3:freq=6500"

        if target_lufs:
            # Measure loudness of the processed graph
            loudnorm_filter = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
            graph += f",{loudnorm_filter},{limiter}[out]"
        else:
            graph += f",{limiter}[out]"

        cmd = [
            _ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", stems["vocals"], "-i", stems["music"],
            "-filter_complex", graph, "-map", "[out]",
            "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "320k", tmp_path
        ]
    else:
        filters = _build_filter_chains(params)
        if target_lufs:
            filters.append(f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11")
        filters.append(limiter)
        chain = ",".join(filters)

        cmd = [
            _ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", audio_path, "-af", chain, "-vn",
            "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "320k", tmp_path
        ]

    if job_id:
        restoration_db.update_job_status(job_id, "processing", 60.0)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=TIMEOUT_S)
        if proc.returncode != 0 or not os.path.isfile(tmp_path):
            err = (proc.stderr or "FFmpeg restoration failed").strip()
            raise RuntimeError(err[:300])
        os.replace(tmp_path, out_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        if job_id:
            restoration_db.update_job_status(job_id, "failed", 0.0, error=str(e))
        raise

    elapsed = round(time.time() - started, 2)
    after_analysis = analyze_audio_file(out_path, max_samples_waveform=100)

    if job_id:
        restoration_db.update_job_status(
            job_id, "completed", 100.0,
            output_path=out_path,
            metrics_after=after_analysis,
            elapsed=elapsed
        )

    return {
        "status": "success",
        "output_path": out_path,
        "preset": preset_key,
        "used_ai_stems": bool(stems),
        "processing_seconds": elapsed,
        "metrics_after": after_analysis,
    }


# ---------------------------------------------------------------------------
# Stage 5: Multi-Format Export
# ---------------------------------------------------------------------------

def export_restored_master(
    source_audio_path: str,
    format_key: str = "mp3_320",
    target_sr: Optional[int] = None
) -> str:
    """Exports restored audio into WAV 16/24/32-bit, MP3 320k, or FLAC."""
    if format_key not in EXPORT_FORMATS:
        format_key = "mp3_320"

    fmt_info = EXPORT_FORMATS[format_key]
    base_name = os.path.splitext(os.path.basename(source_audio_path))[0]
    out_filename = f"{base_name}.{fmt_info['ext']}"
    out_path = os.path.join(RESTORE_DIR, out_filename)

    cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", source_audio_path]
    if target_sr:
        cmd += ["-ar", str(target_sr)]
    cmd += fmt_info["args"] + [out_path]

    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    return out_path
