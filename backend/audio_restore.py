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
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional

try:
    from backend.paths import UPLOAD_DIR
except ImportError:
    from paths import UPLOAD_DIR

CLEAN_DIR = os.path.join(UPLOAD_DIR, "clean")
STRENGTHS = {
    # Archival: Subsonic rumble cut, DC offset, 100% dynamics preserved
    "archival": {"hp": 35, "nr": 6, "nf": -42, "declick": False, "presence": 0.0, "exciter": False},
    # Gentle: Moderate rumble and gentle hiss cut
    "light": {"hp": 40, "nr": 8, "nf": -40, "declick": False, "presence": 1.5, "exciter": False},
    "gentle": {"hp": 40, "nr": 8, "nf": -40, "declick": False, "presence": 1.5, "exciter": False},
    # Vintage: Golden Era studio warmth, tape de-mudding, vocal presence
    "medium": {"hp": 50, "nr": 14, "nf": -35, "declick": True, "presence": 2.5, "exciter": False},
    "vintage": {"hp": 50, "nr": 14, "nf": -35, "declick": True, "presence": 2.5, "exciter": False},
    # Broadcast: Strong hiss cut + high-air sparkle
    "strong": {"hp": 60, "nr": 20, "nf": -28, "declick": True, "presence": 3.5, "exciter": True},
    "broadcast": {"hp": 60, "nr": 20, "nf": -28, "declick": True, "presence": 3.5, "exciter": True},
}
VOICE_BOOST_DB = 3.0
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
    nr = max(4, p["nr"] - 6)
    chain.append(f"afftdn=nr={nr}:nf={p['nf']}")
    chain.append("equalizer=f=300:t=q:w=1.2:g=-2.5")
    chain.append(f"equalizer=f=3500:t=q:w=1.0:g={p['presence'] + 1.0:.1f}")
    chain.append("equalizer=f=8000:t=q:w=1.4:g=2.5")
    chain.append(f"volume={VOICE_BOOST_DB + 0.5:.1f}dB")
    return chain


def _music_chain(p: Dict[str, Any]) -> List[str]:
    """Cleans backing band, widens mono instruments into stereo, and carves a frequency pocket for the voice."""
    chain = [f"highpass=f={p['hp']}"]
    if p["declick"]:
        chain.append("adeclick")
    chain.append(f"afftdn=nr={p['nr']}:nf={p['nf']}")
    chain.append("extrastereo=m=1.4")
    chain.append("equalizer=f=3500:t=q:w=1.0:g=-2.0")
    return chain


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


def clean_song(audio_path: str, strength: str = "medium", voice_forward: bool = False) -> Dict[str, Any]:
    if strength not in STRENGTHS:
        raise CleanError(f"Unknown strength '{strength}'.")
    if not os.path.isfile(audio_path):
        raise CleanError("The song's audio file was not found.")
    p = STRENGTHS[strength]
    stems = _stems(audio_path) if voice_forward else None
    if voice_forward and not stems:
        raise CleanError("Bring the voice forward needs the song's separated voice; VIDA makes it when the song is "
                         "loaded (a few minutes the first time). Try again once it is done.")
    os.makedirs(CLEAN_DIR, exist_ok=True)
    out = clean_path(audio_path, strength, voice_forward)
    tmp = out + ".part.mp3"
    started = time.time()
    if stems:
        voice = ",".join(_voice_chain(p))
        music = ",".join(_music_chain(p))
        graph = f"[0:a]{voice}[v];[1:a]{music}[m];[v][m]amix=inputs=2:normalize=0"
        if p["exciter"]:
            graph += ",aexciter=amount=0.5:drive=3:freq=6500"
        inputs = [stems["vocals"], stems["music"]]
        measured = _measure_loudness(inputs, graph, complex_graph=True)
        cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", inputs[0], "-i", inputs[1],
               "-filter_complex", f"{graph},{_loudness(measured)},{LIMITER}[out]", "-map", "[out]"]
    else:
        chain = ",".join(_repair_chain(p) + _tone_chain(p))
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
    os.replace(tmp, out)
    before, after = _levels(audio_path), _levels(out)
    return {"path": out, "strength": strength, "voice_forward": bool(stems), "seconds": round(time.time() - started, 1),
            "before": before, "after": after}


def existing_clean_versions(audio_path: str) -> List[Dict[str, Any]]:
    base = os.path.splitext(os.path.basename(audio_path))[0]
    if not os.path.isdir(CLEAN_DIR):
        return []
    out = []
    for name in sorted(os.listdir(CLEAN_DIR)):
        m = re.fullmatch(re.escape(base) + r" \[clean (archival|light|gentle|medium|vintage|strong|broadcast)( voice)?\]\.mp3", name)
        if m:
            out.append({"path": os.path.join(CLEAN_DIR, name), "strength": m.group(1), "voice_forward": bool(m.group(2))})
    return out
