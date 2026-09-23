"""
Stage 2 — Vocal Separation with Demucs
Isolates the singing voice from instrumental accompaniment.

Memory strategy: Model is loaded, separation runs, then the model is
explicitly deleted and gc.collect() is called before returning — so
Demucs does NOT stay in RAM during the Whisper transcription stage.
"""

import os
import gc
import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)


def separate_vocals(
    wav_path: str,
    output_dir: str,
    model_name: str = "htdemucs",
    device: str = "cpu",
    shifts: int = 1,
    segment: float = 7.8,
    overlap: float = 0.25,
    jobs: int = 1,
    delete_input_wav: bool = False,
) -> dict:
    """
    Run Demucs vocal separation on a WAV file.

    Args:
        wav_path:     Path to the 16kHz mono input WAV
        output_dir:   Directory to write vocals.wav and accompaniment.wav
        model_name:   Demucs model (htdemucs recommended)
        device:       "cpu" or "cuda"
        shifts:       Random shifts for quality (1 = fastest, 5 = best)
        segment:      Chunk length in seconds (reduce if low RAM)
        overlap:      Overlap between chunks
        jobs:         Parallel workers (keep 1 on CPU)
        delete_input_wav: If True, removes wav_path after separation

    Returns:
        dict with keys:
            vocals:         path to vocals.wav
            accompaniment:  path to accompaniment.wav (no_vocals)
    """
    try:
        import demucs.api as demucs_api
        from demucs.pretrained import get_model
    except ImportError:
        raise ImportError(
            "Demucs is not installed.\n"
            "Run: pip install demucs\n"
            "For CPU-only: ensure torch (CPU build) is installed first."
        )

    wav_path = str(wav_path)
    output_dir = str(output_dir)

    if not os.path.isfile(wav_path):
        raise FileNotFoundError(f"Input WAV not found: {wav_path}")

    os.makedirs(output_dir, exist_ok=True)

    log.info(f"[stage2] Loading Demucs model: {model_name} on {device}")

    # Build separator — this loads the model into RAM
    separator = demucs_api.Separator(
        model=model_name,
        device=device,
        shifts=shifts,
        overlap=overlap,
        segment=segment,
        jobs=jobs,
        progress=True,
    )

    log.info(f"[stage2] Separating vocals: {wav_path}")

    # Run separation
    origin_tensor, separated = separator.separate_audio_file(wav_path)

    stems = separator.model.sources  # e.g. ['drums', 'bass', 'other', 'vocals']
    log.info(f"[stage2] Model stems: {stems}")

    # Save individual stems
    vocals_path = os.path.join(output_dir, "vocals.wav")
    accompaniment_path = os.path.join(output_dir, "accompaniment.wav")

    import torch

    if "vocals" not in stems:
        raise RuntimeError(
            f"Demucs model '{model_name}' does not have a 'vocals' stem. "
            f"Available: {stems}"
        )

    vocals_idx = stems.index("vocals")
    vocals_tensor = separated[stems[vocals_idx]]

    # Build accompaniment = everything except vocals
    non_vocal_stems = [s for s in stems if s != "vocals"]
    if non_vocal_stems:
        accompaniment_tensor = sum(separated[s] for s in non_vocal_stems)
    else:
        accompaniment_tensor = origin_tensor - vocals_tensor

    # Save using demucs audio utilities
    from demucs.audio import save_audio
    sample_rate = separator.samplerate

    save_audio(vocals_tensor, vocals_path, samplerate=sample_rate)
    save_audio(accompaniment_tensor, accompaniment_path, samplerate=sample_rate)

    log.info(f"[stage2] Saved vocals:        {vocals_path}")
    log.info(f"[stage2] Saved accompaniment: {accompaniment_path}")

    # ── Critical: Unload Demucs from RAM before returning ──
    log.info("[stage2] Unloading Demucs model from RAM")
    del separator, origin_tensor, separated
    if "vocals_tensor" in dir():
        del vocals_tensor
    if "accompaniment_tensor" in dir():
        del accompaniment_tensor
    gc.collect()

    # Clean up intermediate input WAV if requested
    if delete_input_wav and os.path.isfile(wav_path):
        os.remove(wav_path)
        log.info(f"[stage2] Deleted temp WAV: {wav_path}")

    return {
        "vocals": vocals_path,
        "accompaniment": accompaniment_path,
    }


def separate_vocals_subprocess(
    wav_path: str,
    output_dir: str,
    model_name: str = "htdemucs",
    device: str = "cpu",
    shifts: int = 1,
    segment: float = 7.8,
    overlap: float = 0.25,
    delete_input_wav: bool = False,
) -> dict:
    """
    Alternative: Run Demucs as a subprocess so it never shares memory
    with the main Python process. Safer for very low-RAM systems.
    Uses the demucs CLI command.
    """
    import subprocess
    import sys

    wav_path = str(wav_path)
    output_dir = str(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        sys.executable, "-m", "demucs",
        "--name", model_name,
        "--device", device,
        "--shifts", str(shifts),
        "--segment", str(segment),
        "--overlap", str(overlap),
        "--out", output_dir,
        "--two-stems", "vocals",   # only separate vocals vs. accompaniment
        wav_path,
    ]

    log.info(f"[stage2] Running Demucs as subprocess: {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Demucs subprocess failed (exit {result.returncode})")

    # Demucs writes to: output_dir/{model_name}/{stem}/{track_name}.wav
    track_name = Path(wav_path).stem
    demucs_out = os.path.join(output_dir, model_name, track_name)

    vocals_raw = os.path.join(demucs_out, "vocals.wav")
    no_vocals_raw = os.path.join(demucs_out, "no_vocals.wav")

    # Move to flat structure
    vocals_path = os.path.join(output_dir, "vocals.wav")
    accompaniment_path = os.path.join(output_dir, "accompaniment.wav")

    if os.path.isfile(vocals_raw):
        shutil.move(vocals_raw, vocals_path)
    if os.path.isfile(no_vocals_raw):
        shutil.move(no_vocals_raw, accompaniment_path)

    # Clean up nested folders
    demucs_root = os.path.join(output_dir, model_name)
    if os.path.isdir(demucs_root):
        shutil.rmtree(demucs_root, ignore_errors=True)

    if delete_input_wav and os.path.isfile(wav_path):
        os.remove(wav_path)
        log.info(f"[stage2] Deleted temp WAV: {wav_path}")

    log.info(f"[stage2] vocals → {vocals_path}")
    log.info(f"[stage2] accompaniment → {accompaniment_path}")

    return {
        "vocals": vocals_path,
        "accompaniment": accompaniment_path,
    }
