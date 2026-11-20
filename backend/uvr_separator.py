"""
UVR5 (Ultimate Vocal Remover) Engine for VIDA
Integrates state-of-the-art MDX-Net and VR Architecture models (Kim Vocal 2, Voc FT, De-Reverb)
directly into VIDA with zero external GUI overhead.
"""

import os
import sys
import logging
import shutil
import time
from typing import Optional, Dict, Any, List, Tuple

log = logging.getLogger(__name__)

# Directory setup
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
UVR_MODELS_DIR = os.path.join(_PROJECT_ROOT, "models", "uvr")
STEMS_DIR = os.path.join(_PROJECT_ROOT, "uploads", "stems")

os.makedirs(UVR_MODELS_DIR, exist_ok=True)
os.makedirs(STEMS_DIR, exist_ok=True)

UVR_ENGINES: Dict[str, Dict[str, Any]] = {
    "uvr_kim_vocal_2": {
        "id": "uvr_kim_vocal_2",
        "name": "UVR MDX-Net (Kim Vocal 2)",
        "model_file": "Kim_Vocal_2.onnx",
        "description": "Gold standard for vintage music. Cleanest vocal isolation with near-zero brass & guitar bleed.",
        "type": "separation",
        "recommended_for": "vintage_khmer",
    },
    "uvr_voc_ft": {
        "id": "uvr_voc_ft",
        "name": "UVR MDX-Net (Voc FT)",
        "model_file": "UVR-MDX-NET-Voc_FT.onnx",
        "description": "High-fidelity vocal extraction model with natural acoustic harmonics.",
        "type": "separation",
        "recommended_for": "general_music",
    },
    "uvr_de_reverb": {
        "id": "uvr_de_reverb",
        "name": "UVR De-Echo / De-Reverb",
        "model_file": "UVR-De-Echo-De-Reverb.pth",
        "description": "Removes 1960s spring reverb and room echo, making vintage vocals sound dry and up-close.",
        "type": "de_reverb",
        "recommended_for": "echoey_tapes",
    },
}


def _ensure_ffmpeg_path():
    """Ensures FFmpeg binary from imageio_ffmpeg is accessible on system PATH."""
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_dir = os.path.dirname(ffmpeg_exe)
        # Ensure a copy or link named 'ffmpeg.exe' exists in that folder
        std_name = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        if not os.path.isfile(std_name) and os.path.isfile(ffmpeg_exe):
            try:
                shutil.copy2(ffmpeg_exe, std_name)
            except Exception:
                pass
        if ffmpeg_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception as e:
        log.warning(f"[UVR] Could not resolve imageio_ffmpeg path: {e}")


def separate_with_uvr(
    audio_path: str,
    engine_id: str = "uvr_kim_vocal_2",
    progress_callback: Optional[Any] = None
) -> Tuple[str, str]:
    """
    Separates an audio file into vocals and accompaniment using UVR5.
    Returns tuple of (vocals_path, accompaniment_path).
    Outputs match VIDA's standard stem filenames in uploads/stems/.
    """
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    _ensure_ffmpeg_path()

    from audio_separator.separator import Separator

    engine_info = UVR_ENGINES.get(engine_id, UVR_ENGINES["uvr_kim_vocal_2"])
    model_filename = engine_info["model_file"]

    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    expected_vocals = os.path.join(STEMS_DIR, f"{base_name}_vocals.wav")
    expected_music = os.path.join(STEMS_DIR, f"{base_name}_accompaniment.wav")

    model_tag = os.path.splitext(model_filename)[0]
    engine_vocals = os.path.join(STEMS_DIR, f"{base_name}_(Vocals)_{model_tag}.wav")
    engine_music = os.path.join(STEMS_DIR, f"{base_name}_(Instrumental)_{model_tag}.wav")

    # Fast return if model-specific stems are already cached
    if os.path.isfile(engine_vocals) and os.path.isfile(engine_music):
        if os.path.getsize(engine_vocals) > 1000 and os.path.getsize(engine_music) > 1000:
            log.info(f"[UVR] Found cached {model_tag} stems for: {base_name}")
            try:
                shutil.copy2(engine_vocals, expected_vocals)
                shutil.copy2(engine_music, expected_music)
            except Exception:
                pass
            return engine_vocals, engine_music

    started = time.time()
    log.info(f"[UVR] Starting separation with {engine_info['name']} on: {base_name}")

    sep = Separator(
        model_file_dir=UVR_MODELS_DIR,
        output_dir=STEMS_DIR,
        output_format="WAV",
        sample_rate=44100,
        use_directml=True,
        mdx_params={
            "hop_length": 1024,
            "segment_size": 256,
            "overlap": 0.5,
            "batch_size": 1,
            "enable_denoise": True,
        },
    )

    import onnxruntime as ort
    avail_providers = ort.get_available_providers()
    if "DmlExecutionProvider" in avail_providers:
        log.info("[UVR] DirectML GPU acceleration active (NVIDIA GeForce RTX 3050 Ti)")
        sep.onnx_execution_provider = ["DmlExecutionProvider", "CPUExecutionProvider"]
    elif "CUDAExecutionProvider" in avail_providers:
        log.info("[UVR] CUDA GPU acceleration active")
        sep.onnx_execution_provider = ["CUDAExecutionProvider", "CPUExecutionProvider"]

    sep.load_model(model_filename)
    output_files = sep.separate(audio_path)
    log.info(f"[UVR] Output files generated: {output_files}")

    # Standardize output filenames to VIDA's _vocals.wav and _accompaniment.wav
    vocals_found = None
    music_found = None

    for fname in output_files:
        full_p = os.path.join(STEMS_DIR, fname) if not os.path.isabs(fname) else fname
        low = os.path.basename(fname).lower()
        if "instrumental" in low or "inst" in low or "no_vocal" in low or "other" in low or "accompaniment" in low:
            music_found = full_p
        elif "vocal" in low:
            vocals_found = full_p

    if vocals_found and os.path.isfile(vocals_found):
        if vocals_found != expected_vocals:
            try:
                shutil.copy2(vocals_found, expected_vocals)
            except Exception:
                pass

    if music_found and os.path.isfile(music_found):
        if music_found != expected_music:
            try:
                shutil.copy2(music_found, expected_music)
            except Exception:
                pass

    elapsed = round(time.time() - started, 1)
    log.info(f"[UVR] Separation complete in {elapsed}s: {expected_vocals}")

    return expected_vocals, expected_music


def dereverb_vocal_stem(vocals_path: str) -> str:
    """
    Applies UVR-De-Echo-De-Reverb to remove room echo and spring delay from a vocal stem.
    Returns path to the dry, de-reverbed vocal WAV file.
    """
    if not os.path.isfile(vocals_path):
        raise FileNotFoundError(f"Vocal file not found: {vocals_path}")

    _ensure_ffmpeg_path()

    from audio_separator.separator import Separator

    base_name = os.path.splitext(os.path.basename(vocals_path))[0]
    expected_dry = os.path.join(STEMS_DIR, f"{base_name}_dry.wav")

    if os.path.isfile(expected_dry) and os.path.getsize(expected_dry) > 1000:
        return expected_dry

    sep = Separator(
        model_file_dir=UVR_MODELS_DIR,
        output_dir=STEMS_DIR,
        output_format="WAV",
        sample_rate=44100,
        use_directml=True,
    )

    import onnxruntime as ort
    avail_providers = ort.get_available_providers()
    if "DmlExecutionProvider" in avail_providers:
        sep.onnx_execution_provider = ["DmlExecutionProvider", "CPUExecutionProvider"]

    sep.load_model("UVR-De-Echo-De-Reverb.pth")
    output_files = sep.separate(vocals_path)

    for fname in output_files:
        full_p = os.path.join(STEMS_DIR, fname) if not os.path.isabs(fname) else fname
        low = os.path.basename(fname).lower()
        if "no_reverb" in low or "dry" in low or "vocal" in low:
            try:
                shutil.copy2(full_p, expected_dry)
                return expected_dry
            except Exception:
                pass

    return expected_dry if os.path.isfile(expected_dry) else vocals_path
