"""
Vocal Separation Module for VIDA.
Uses Demucs (htdemucs) to isolate pure vocals from instruments and music.
Includes caching, progress reporting, and graceful acoustic filtering fallback.

Demucs runs in a throwaway child process. This machine sits close to its commit limit, and a
long-lived server that has mapped torch's CUDA context leaves too little address space for the
next model to load: torch's reader faults (exit 139) instead of raising, killing the server and
every sync request in flight. One short process per model keeps the peak at a single model.
"""

import os
import gc
import sys
import json
import shutil
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Callable, Dict, Any

try:
    from backend.model_job import run_locked
except ImportError:
    from model_job import run_locked

# Enable offline mode for HuggingFace if model is cached locally
# This completely prevents "ReadTimeoutError: HTTPSConnectionPool(host='huggingface.co', port=443)"
_hf_cache = os.path.expanduser("~/.cache/huggingface/hub/models--adefossez--HTDemucs")
if os.path.exists(_hf_cache):
    os.environ["HF_HUB_OFFLINE"] = "1"

log = logging.getLogger(__name__)

# Cache directory for isolated stems
STEMS_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads", "stems")
os.makedirs(STEMS_CACHE_DIR, exist_ok=True)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROGRESS_PREFIX = "VIDA_STEM|"
_SEPARATION_TIMEOUT_S = 1800.0
_CUDA_OK = None


def missing_dependency() -> Optional[str]:
    """First package Demucs needs that this interpreter cannot see, or None when it can run."""
    import importlib.util
    for module in ("demucs", "torch"):
        try:
            if importlib.util.find_spec(module) is None:
                return module
        except (ImportError, ValueError):
            return module
    return None


def cuda_available() -> bool:
    """Reports whether a GPU can separate vocals, probed once in a child so the server stays torch-free."""
    global _CUDA_OK
    if _CUDA_OK is None:
        try:
            proc = subprocess.run(
                [sys.executable, "-c", "import torch; print('CUDA' if torch.cuda.is_available() else 'CPU')"],
                cwd=_REPO_ROOT, capture_output=True, text=True, timeout=300,
            )
            _CUDA_OK = "CUDA" in proc.stdout
        except Exception as e:
            print(f"[Demucs] CUDA probe failed, assuming CPU: {e}")
            _CUDA_OK = False
    return _CUDA_OK


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
) -> Dict[str, Any]:
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

    # 2. Otherwise separate in a child process that hands all its memory back when it exits
    return _separate_in_child(audio_path, vocals_out, accompaniment_out, device, model_name, progress_callback)


def _separate_in_child(
    audio_path: str,
    vocals_out: str,
    accompaniment_out: str,
    device: str,
    model_name: str,
    progress_callback: Optional[Callable[[int, str], None]]
) -> Dict[str, Any]:
    fd, out_path = tempfile.mkstemp(prefix="vida_stem_result_", suffix=".json")
    os.close(fd)
    os.remove(out_path)
    cmd = [sys.executable, "-m", "backend.demucs_worker", audio_path, out_path,
           vocals_out, accompaniment_out, model_name, device]
    try:
        return run_locked(lambda: _spawn_separator(cmd, out_path, audio_path, progress_callback))
    except TimeoutError as busy:
        print(f"[Demucs] {busy}. Falling back to the original audio.")
        return {"vocals": audio_path, "accompaniment": "", "error": str(busy)}
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass


def _spawn_separator(cmd, out_path, audio_path, progress_callback):
    """Runs one Demucs child alone; two torch models loading at once exhaust commit space and fault."""
    try:
        proc = subprocess.Popen(
            cmd, cwd=_REPO_ROOT, text=True, encoding="utf-8", errors="replace",
            env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            if not line.startswith(_PROGRESS_PREFIX) or progress_callback is None:
                continue
            pct, _, msg = line[len(_PROGRESS_PREFIX):].partition("|")
            try:
                progress_callback(int(pct), msg)
            except (TypeError, ValueError):
                pass
        code = proc.wait(timeout=_SEPARATION_TIMEOUT_S)
        if not os.path.exists(out_path):
            print(f"[Demucs] Separator process exited {code:#x}. Falling back to the original audio.")
            return {"vocals": audio_path, "accompaniment": "", "error": f"separator exited {code:#x}"}
        with open(out_path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as e:
        print(f"[Demucs] Separator process failed: {e}. Falling back to the original audio.")
        if progress_callback:
            progress_callback(25, f"Demucs notice: {e}, continuing...")
        return {"vocals": audio_path, "accompaniment": "", "error": str(e)}


def _separate_inproc(
    audio_path: str,
    vocals_out: str,
    accompaniment_out: str,
    device: str = "cpu",
    model_name: str = "htdemucs",
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Dict[str, Any]:
    """The Demucs run itself. Only ever called inside backend.demucs_worker."""
    # 1. Try importing Demucs
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
        progress_callback(20, f"Loading Demucs ({model_name}) vocal separator...")

    # Enable HuggingFace offline mode if model already cached locally to prevent network timeouts
    hf_cache = os.path.expanduser(f"~/.cache/huggingface/hub/models--adefossez--HTDemucs")
    if os.path.exists(hf_cache):
        os.environ["HF_HUB_OFFLINE"] = "1"

    try:
        # Build Demucs separator (retry with offline mode if network check times out)
        try:
            separator = demucs_api.Separator(
                model=model_name,
                device=device,
                shifts=1,      # 1 shift for maximum speed on CPU
                overlap=0.25,
                segment=7.8,
                jobs=min(4, os.cpu_count() or 1),
                progress=False
            )
        except Exception as load_err:
            print(f"[Demucs] Notice loading model: {load_err}. Retrying in local offline mode...")
            os.environ["HF_HUB_OFFLINE"] = "1"
            separator = demucs_api.Separator(
                model=model_name,
                device=device,
                shifts=1,
                overlap=0.25,
                segment=7.8,
                jobs=min(4, os.cpu_count() or 1),
                progress=False
            )

        if progress_callback:
            progress_callback(25, "Separating vocals from instruments...")

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
