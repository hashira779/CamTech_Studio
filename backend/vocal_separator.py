"""
Vocal Separation Module for VIDA.
Uses Demucs (htdemucs) to isolate pure vocals from instruments and music.
Includes caching, progress reporting, and graceful acoustic filtering fallback.
"""

import os
import gc
import sys
import shutil
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any

log = logging.getLogger(__name__)

# Cache directory for isolated stems
STEMS_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads", "stems")
os.makedirs(STEMS_CACHE_DIR, exist_ok=True)


def get_cached_vocals_path(audio_path: str) -> Optional[str]:
    """Checks if vocals were already isolated for this audio file."""
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    expected_vocals = os.path.join(STEMS_CACHE_DIR, f"{base_name}_vocals.wav")
    if os.path.isfile(expected_vocals) and os.path.getsize(expected_vocals) > 10000:
        return expected_vocals
    return None


def separate_vocals_demucs(
    audio_path: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    device: str = "cpu",
    model_name: str = "htdemucs"
) -> Dict[str, str]:
    """
    Isolates singing vocals from background instruments using Demucs.
    Returns dict with 'vocals' and 'accompaniment' file paths.
    """
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    vocals_out = os.path.join(STEMS_CACHE_DIR, f"{base_name}_vocals.wav")
    accompaniment_out = os.path.join(STEMS_CACHE_DIR, f"{base_name}_accompaniment.wav")

    # 1. Return cached stem if available
    if os.path.isfile(vocals_out) and os.path.getsize(vocals_out) > 10000:
        if progress_callback:
            progress_callback(30, "Found cached isolated vocals! (Instant)")
        print(f"[Demucs] Reusing cached vocals: {vocals_out}")
        return {
            "vocals": vocals_out,
            "accompaniment": accompaniment_out,
            "cached": True
        }

    # 2. Try importing Demucs
    try:
        import demucs.api as demucs_api
        import torch
    except ImportError:
        print("[Demucs] demucs or torch not installed. Falling back to frequency vocal filter.")
        if progress_callback:
            progress_callback(25, "Demucs not installed, using vocal filter fallback...")
        return {
            "vocals": audio_path,
            "accompaniment": "",
            "fallback": True
        }

    if progress_callback:
        progress_callback(10, f"Loading Demucs ({model_name}) vocal separator...")

    try:
        # Build Demucs separator
        separator = demucs_api.Separator(
            model=model_name,
            device=device,
            shifts=1,      # 1 shift for maximum speed on CPU
            overlap=0.25,
            segment=7.8,
            jobs=min(4, os.cpu_count() or 1),
            progress=False
        )

        if progress_callback:
            progress_callback(20, "Separating vocals from instruments...")

        origin_tensor, separated = separator.separate_audio_file(audio_path)
        stems = separator.model.sources

        if "vocals" not in stems:
            raise RuntimeError(f"Demucs model '{model_name}' has no vocals stem. Stems: {stems}")

        vocals_idx = stems.index("vocals")
        vocals_tensor = separated[stems[vocals_idx]]

        # Accompaniment = mix of all non-vocal stems
        non_vocal_stems = [s for s in stems if s != "vocals"]
        if non_vocal_stems:
            accompaniment_tensor = sum(separated[s] for s in non_vocal_stems)
        else:
            accompaniment_tensor = origin_tensor - vocals_tensor

        from demucs.audio import save_audio
        sr = separator.samplerate

        if progress_callback:
            progress_callback(35, "Saving isolated vocal tracks...")

        save_audio(vocals_tensor, vocals_out, samplerate=sr)
        save_audio(accompaniment_tensor, accompaniment_out, samplerate=sr)

        # Free RAM immediately so ASR model has room to run
        del separator, origin_tensor, separated, vocals_tensor, accompaniment_tensor
        gc.collect()

        if progress_callback:
            progress_callback(40, "Vocals cleanly isolated from instruments!")

        print(f"[Demucs] Successfully separated vocals: {vocals_out}")
        return {
            "vocals": vocals_out,
            "accompaniment": accompaniment_out,
            "cached": False
        }

    except Exception as e:
        print(f"[Demucs] Error during separation: {e}. Falling back to original audio.")
        if progress_callback:
            progress_callback(25, f"Demucs notice: {e}, continuing...")
        return {
            "vocals": audio_path,
            "accompaniment": "",
            "error": str(e)
        }
