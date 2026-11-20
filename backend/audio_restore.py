"""
Clean an old recording for listening: less rumble, crackle and tape hiss, a clearer voice and an
even, modern loudness. Built from ffmpeg's own filters, so nothing is downloaded and it runs fast on
the CPU. The original file is never changed: the cleaned copy goes to uploads/clean/.

  light   rumble cut, gentle hiss reduction, a little voice presence, loudness
  medium  + crackle and click removal, stronger hiss reduction
  strong  + strongest hiss reduction and a touch of high-end sparkle for dull tape

"Bring the voice forward" remixes the song from its separated voice and music (the stems VIDA makes
for alignment) with the voice 3 dB louder and each part cleaned on its own; old recordings often
have the singer sitting far behind the band.
"""
import logging
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

try:
    from backend.paths import UPLOAD_DIR
except ImportError:
    from paths import UPLOAD_DIR

CLEAN_DIR = os.path.join(UPLOAD_DIR, "clean")
STRENGTHS = {
    # Archival: Subsonic rumble cut, DC offset, 100% dynamics preserved
    "archival": {"hp": 28, "nr": 4, "nf": -45, "declick": False, "presence": 0.0, "exciter": False},
    # Gentle: Moderate rumble and gentle hiss cut, natural instrument body
    "light": {"hp": 30, "nr": 6, "nf": -42, "declick": False, "presence": 1.2, "exciter": False},
    "gentle": {"hp": 30, "nr": 6, "nf": -42, "declick": False, "presence": 1.2, "exciter": False},
    # Vintage: Golden Era studio warmth, tape de-mudding, vocal presence
    "medium": {"hp": 32, "nr": 8, "nf": -38, "declick": True, "presence": 2.0, "exciter": False},
    "vintage": {"hp": 32, "nr": 8, "nf": -38, "declick": True, "presence": 2.0, "exciter": False},
    # UVR Stems: Kim Vocal 2 isolation + full backing band body, instrument warmth & feeling
    "uvr_stems": {"hp": 32, "nr": 8, "nf": -36, "declick": False, "presence": 2.0, "exciter": False},
    # Broadcast: Maximum clarity & high-end air sparkle
    "strong": {"hp": 35, "nr": 12, "nf": -34, "declick": True, "presence": 2.5, "exciter": True},
    "broadcast": {"hp": 35, "nr": 12, "nf": -34, "declick": True, "presence": 2.5, "exciter": True},
}
VOICE_BOOST_DB = 1.2
# Streaming loudness (YouTube / Facebook play around -14 LUFS). Measured first, then applied to the
# whole song evenly (loudnorm's linear mode): one-pass loudnorm and a compressor lifted the soft
# passages and the tape hiss in them, which undid the hiss reduction (ផ្ការីកក្នុងចិត្ត: +2.3 dB).
TARGET = "I=-14:TP=-1.5:LRA=11"
TARGET_LUFS = -14.0
# A hard ceiling at -1.5 dBFS: the one-pass version let peaks reach +0.9 dBFS, which distorts.
LIMITER = "alimiter=limit=0.84:attack=5:release=50:level=false"
TIMEOUT_S = 1200


class CleanError(Exception):
    """A reason the song could not be cleaned, in words the studio can show."""


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def clean_path(audio_path: str, strength: str, voice_forward: bool) -> str:
    base = os.path.splitext(os.path.basename(audio_path))[0]
    tag = strength + (" voice" if voice_forward else "")
    return os.path.join(CLEAN_DIR, f"{base} [clean {tag}].mp3")


def _voice_chain(p: Dict[str, Any]) -> List[str]:
    """Polishes vocal stem: cuts mic rumble, cleans hiss, dips 300Hz mud, and lifts clarity & air."""
    chain = ["highpass=f=75"]
    if p["declick"]:
        chain.append("adeclick")
    nr = max(3, p["nr"] - 4)
    chain.append(f"afftdn=nr={nr}:nf={p['nf']}")
    chain.append("equalizer=f=300:t=q:w=1.2:g=-2.0")
    chain.append(f"equalizer=f=3200:t=q:w=1.0:g={p['presence']:.1f}")
    chain.append("equalizer=f=8000:t=q:w=1.2:g=1.5")
    chain.append(f"volume={VOICE_BOOST_DB:.1f}dB")
    return chain


def _music_chain(p: Dict[str, Any]) -> List[str]:
    """
    Preserves backing band warmth, bass punch and feeling:
    - Gentle 32Hz subsonic protection (preserves electric/upright bass fundamentals & kick drums)
    - Gentle hiss smoothing (never smears acoustic instrument attacks or room decay)
    - Adds analog body warmth around 100Hz and crisp instrument definition
    - Retains full mono/center punch (no destructive extrastereo phase cancellation)
    """
    chain = ["highpass=f=32"]
    # Only light noise smoothing on backing music so acoustic nuance and room feel remain intact
    chain.append(f"afftdn=nr={max(2, min(5, p['nr'] // 2))}:nf={p['nf'] - 4}")
    # Analog low-end warmth & punch (bass guitar & drums)
    chain.append("equalizer=f=100:t=q:w=1.0:g=1.8")
    # Instrument clarity and brilliance without harshness
    chain.append("equalizer=f=2800:t=q:w=1.2:g=1.0")
    chain.append("equalizer=f=10000:t=q:w=1.0:g=1.2")
    # Balance backing band presence alongside the vocalist
    chain.append("volume=0.8dB")
    return chain


def _master_eq_chain(eq_sub: float = 0.0, eq_mid: float = 0.0, eq_high: float = 0.0) -> List[str]:
    """Applies master 3-band tone shaping (Sub 60Hz, Mid 2.5kHz, High 10kHz) to the rendered audio."""
    filters = []
    if abs(eq_sub) > 0.05:
        filters.append(f"equalizer=f=60:t=q:w=1.0:g={eq_sub:.1f}")
    if abs(eq_mid) > 0.05:
        filters.append(f"equalizer=f=2500:t=q:w=1.0:g={eq_mid:.1f}")
    if abs(eq_high) > 0.05:
        filters.append(f"equalizer=f=10000:t=q:w=1.0:g={eq_high:.1f}")
    return filters


def _repair_chain(p: Dict[str, Any], voice_part: bool = False) -> List[str]:
    """Rumble, crackle and hiss, in that order (clicks are found more reliably before denoising)."""
    chain = [f"highpass=f={p['hp']}"]
    if p["declick"]:
        chain.append("adeclick")
    # A separated voice carries less hiss than the full mix: lighter reduction keeps it natural.
    nr = max(4, p["nr"] - 6) if voice_part else p["nr"]
    # A fixed noise floor, not noise tracking (tn=1): tracking learns the "noise" from the song's start, a
    # silent intro taught it silence, and it then removed nothing (ផ្ការីកក្នុងចិត្ត: hiss +0.0 dB vs -13.9).
    chain.append(f"afftdn=nr={nr}:nf={p['nf']}")
    return chain


def _tone_chain(p: Dict[str, Any]) -> List[str]:
    """Less boxiness and more voice presence (loudness and the limiter are added per pass)."""
    chain = ["equalizer=f=250:t=q:w=1:g=-1.5", f"equalizer=f=3200:t=q:w=1.2:g={p['presence']}"]
    if p["exciter"]:
        chain.append("aexciter=amount=0.6:drive=4:freq=6000")
    return chain


def _measure_loudness(inputs: List[str], graph_or_chain: str, complex_graph: bool) -> Dict[str, str]:
    """First pass: the song's loudness after cleaning, for an even (linear) second pass."""
    import json
    cmd = [_ffmpeg(), "-hide_banner", "-nostats", "-y"]
    for i in inputs:
        cmd += ["-i", i]
    if complex_graph:
        cmd += ["-filter_complex", graph_or_chain + f",loudnorm={TARGET}:print_format=json[out]", "-map", "[out]"]
    else:
        cmd += ["-af", graph_or_chain + f",loudnorm={TARGET}:print_format=json"]
    cmd += ["-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=TIMEOUT_S)
    text = proc.stderr or ""
    start = text.rfind("{")
    try:
        m = json.loads(text[start:text.rfind("}") + 1])
        return {k: m[k] for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
    except (ValueError, KeyError):
        raise CleanError("Could not measure the song's loudness.")


def _loudness(m: Dict[str, str]) -> str:
    """
    One even gain to -14 LUFS; the limiter after it catches the peaks. Not loudnorm's second pass:
    when its linear gain would break the peak target it silently switches to dynamic mode, which
    lifts soft passages and their hiss (it cancelled a 14 dB hiss reduction on ផ្ការីកក្នុងចិត្ត).
    """
    gain = max(-20.0, min(20.0, TARGET_LUFS - float(m["input_i"])))
    return f"volume={gain:.2f}dB"


def _stems(audio_path: str) -> Optional[Dict[str, str]]:
    try:
        from backend.vocal_align import get_cached_vocals_path
    except ImportError:
        from vocal_align import get_cached_vocals_path
    vocals = get_cached_vocals_path(audio_path)
    if not vocals:
        return None
    music = vocals.replace("_vocals.wav", "_accompaniment.wav")
    return {"vocals": vocals, "music": music} if os.path.isfile(music) else None


def voice_forward_available(audio_path: str) -> bool:
    return _stems(audio_path) is not None


def _levels(path: str) -> Dict[str, float]:
    """Noise floor (quietest 10% of 50 ms frames) and overall level, in dBFS."""
    import numpy as np
    try:
        from backend.audio_analyzer import decode_audio_to_numpy
    except ImportError:
        from audio_analyzer import decode_audio_to_numpy
    data, sr, _ = decode_audio_to_numpy(path, target_sr=16000)
    if data.ndim > 1:
        data = data.mean(axis=1)
    hop = int(0.05 * sr)
    frames = data[: len(data) // hop * hop].reshape(-1, hop)
    rms = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1)) + 1e-9
    db = 20 * np.log10(rms)
    loud = db[db > np.percentile(db, 10)]
    return {"noise_floor_db": round(float(np.percentile(db, 10)), 1),
            "level_db": round(float(20 * np.log10(np.sqrt(np.mean(10 ** (loud / 10))))), 1)}


def _safe_replace(tmp: str, out: str, max_retries: int = 6, delay: float = 0.25) -> str:
    """Replaces out with tmp on Windows, handling open file locks with retries and timestamp fallback."""
    for attempt in range(max_retries):
        try:
            if os.name == "nt" and os.path.exists(out):
                try:
                    os.remove(out)
                except OSError:
                    pass
            os.replace(tmp, out)
            return out
        except OSError:
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                dir_name, file_name = os.path.split(out)
                base, ext = os.path.splitext(file_name)
                fallback_out = os.path.join(dir_name, f"{base}_{int(time.time())}{ext}")
                try:
                    os.replace(tmp, fallback_out)
                    return fallback_out
                except Exception as fallback_err:
                    raise CleanError(f"Audio file is locked by the player. Please pause playback and try again: {fallback_err}")
    return out


def clean_song(
    audio_path: str,
    strength: str = "medium",
    voice_forward: bool = False,
    stem_engine: str = "uvr_kim_vocal_2",
    eq_sub: float = 0.0,
    eq_mid: float = 0.0,
    eq_high: float = 0.0,
) -> Dict[str, Any]:
    if strength not in STRENGTHS:
        raise CleanError(f"Unknown strength '{strength}'.")
    if not os.path.isfile(audio_path):
        raise CleanError("The song's audio file was not found.")
    p = STRENGTHS[strength]
    stems = None
    if voice_forward:
        if stem_engine and stem_engine.startswith("uvr_"):
            try:
                from backend import uvr_separator
                voc, mus = uvr_separator.separate_with_uvr(audio_path, engine_id=stem_engine)
                if os.path.isfile(voc) and os.path.isfile(mus):
                    stems = {"vocals": voc, "music": mus}
            except Exception as e:
                log.warning(f"[Clean] UVR stem separation issue with {stem_engine}: {e}")
        if not stems:
            stems = _stems(audio_path)
        if not stems:
            try:
                from backend.vocal_align import _ensure_vocal_stem
                voc = _ensure_vocal_stem(audio_path)
                if voc:
                    mus = voc.replace("_vocals.wav", "_accompaniment.wav")
                    if os.path.isfile(mus):
                        stems = {"vocals": voc, "music": mus}
            except Exception as fb_err:
                log.warning(f"[Clean] Fallback stem separation also failed: {fb_err}")
            if not stems:
                raise CleanError("Voice separation could not be completed. Please try again.")
    if voice_forward and not stems:
        raise CleanError("Bring the voice forward needs the song's separated voice; please try again in a moment.")
    os.makedirs(CLEAN_DIR, exist_ok=True)
    out = clean_path(audio_path, strength, voice_forward)
    tmp = out + ".part.mp3"
    started = time.time()
    master_eq_parts = _master_eq_chain(eq_sub, eq_mid, eq_high)
    master_eq_str = ("," + ",".join(master_eq_parts)) if master_eq_parts else ""
    if stems:
        voice = ",".join(_voice_chain(p))
        music = ",".join(_music_chain(p))
        graph = f"[0:a]{voice}[v];[1:a]{music}[m];[v][m]amix=inputs=2:normalize=0{master_eq_str}"
        if p["exciter"]:
            graph += ",aexciter=amount=0.4:drive=2.5:freq=6500"
        inputs = [stems["vocals"], stems["music"]]
        measured = _measure_loudness(inputs, graph, complex_graph=True)
        cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", inputs[0], "-i", inputs[1],
               "-filter_complex", f"{graph},{_loudness(measured)},{LIMITER}[out]", "-map", "[out]"]
    else:
        chain = ",".join(_repair_chain(p) + _tone_chain(p) + master_eq_parts)
        measured = _measure_loudness([audio_path], chain, complex_graph=False)
        cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", audio_path,
               "-af", f"{chain},{_loudness(measured)},{LIMITER}", "-vn"]
    cmd += ["-ar", "44100", "-c:a", "libmp3lame", "-b:a", "320k", tmp]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise CleanError("Cleaning took too long and was stopped.")
    if proc.returncode != 0 or not os.path.isfile(tmp):
        last = (proc.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        raise CleanError(f"ffmpeg could not clean the song: {last[0][:200]}")
    final_out = _safe_replace(tmp, out)
    before, after = _levels(audio_path), _levels(final_out)
    return {"path": final_out, "strength": strength, "voice_forward": bool(stems), "seconds": round(time.time() - started, 1),
            "before": before, "after": after}


def existing_clean_versions(audio_path: str) -> List[Dict[str, Any]]:
    base = os.path.splitext(os.path.basename(audio_path))[0]
    if not os.path.isdir(CLEAN_DIR):
        return []
    out = []
    for name in sorted(os.listdir(CLEAN_DIR)):
        m = re.fullmatch(re.escape(base) + r" \[clean (archival|light|gentle|medium|vintage|uvr_stems|strong|broadcast)( voice)?\](?:_\d+)?\.mp3", name)
        if m:
            out.append({"path": os.path.join(CLEAN_DIR, name), "strength": m.group(1), "voice_forward": bool(m.group(2))})
    return out
