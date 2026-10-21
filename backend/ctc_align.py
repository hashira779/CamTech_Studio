"""
Word-level lyric-to-singer alignment with the multilingual MMS wav2vec2 CTC aligner.

Lyrics are romanized with uroman (Khmer, Vietnamese, Thai, ... -> latin letters), the acoustic
model produces per-frame letter probabilities (20 ms frames), and CTC forced alignment finds the
single most likely monotonic path of every lyric letter through the song. A penalised "garbage"
token between lines absorbs ad-libs, humming or repeated choruses missing from the lyrics.
"""

import os
import sys
import logging
import threading
import unicodedata
from typing import List, Dict, Any, Optional, Tuple

try:
    from backend.model_job import run_locked
except ImportError:
    from model_job import run_locked

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
_HOP = 320
_FRAME_S = _HOP / SAMPLE_RATE
_CHUNK_S = 30.0
_CONTEXT_S = 1.5
_STAR_LOGP = -4.0
MIN_CONFIDENCE = 0.25

_LOCK = threading.Lock()
_MODEL = None
_DICT: Dict[str, int] = {}
_UROMAN = None
_EMISSION_CACHE: Dict[Tuple[str, float], Any] = {}


def _get_model():
    global _MODEL, _DICT
    with _LOCK:
        if _MODEL is None:
            import gc
            import torch
            import torchaudio
            # Demucs leaves its CUDA blocks reserved, and torch's zip reader faults while
            # mapping the aligner checkpoint into that pressure (hard crash, not an exception).
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            bundle = torchaudio.pipelines.MMS_FA
            model = bundle.get_model(with_star=False, dl_kwargs={"weights_only": True, "map_location": "cpu"})
            model.eval()
            torch.set_grad_enabled(False)
            _DICT = bundle.get_dict(star=None)
            _MODEL = model
    return _MODEL, _DICT


def _get_uroman():
    global _UROMAN
    with _LOCK:
        if _UROMAN is None:
            import uroman as ur
            _UROMAN = ur.Uroman()
    return _UROMAN


def missing_dependency() -> Optional[str]:
    """
    Name of the first package this interpreter cannot see, or None when the aligner can run.
    Resolved without importing: mapping torch into the web process leaves the aligner child too
    little address space to load its checkpoint, which faults instead of raising.
    """
    import importlib.util
    for module in ("torch", "torchaudio", "uroman"):
        try:
            if importlib.util.find_spec(module) is None:
                return module
        except (ImportError, ValueError):
            return module
    return None


def is_available() -> bool:
    return missing_dependency() is None


def _lang_code(text: str) -> Optional[str]:
    for ch in text:
        o = ord(ch)
        if 0x1780 <= o <= 0x17FF:
            return "khm"
        if 0x0E00 <= o <= 0x0E7F:
            return "tha"
        if 0x0E80 <= o <= 0x0EFF:
            return "lao"
        if 0x1000 <= o <= 0x109F:
            return "mya"
    return None


def _romanize(word: str, lcode: Optional[str], vocab: Dict[str, int]) -> List[int]:
    s = word if word.isascii() else _get_uroman().romanize_string(word, lcode=lcode)
    s = unicodedata.normalize("NFKD", str(s).lower())
    return [vocab[c] for c in s if c in vocab and c != "-"]


def _load_audio(audio_path: str):
    import numpy as np
    try:
        from backend.audio_analyzer import decode_audio_to_numpy
    except ImportError:
        from audio_analyzer import decode_audio_to_numpy
    data, sr, _ = decode_audio_to_numpy(audio_path, target_sr=SAMPLE_RATE)
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    return data.astype(np.float32, copy=False)


def compute_emission(audio_path: str):
    """Per-frame log-probabilities (T, C) over the aligner vocabulary, cached per file."""
    import torch
    try:
        from backend.vocal_align import get_cached_vocals_path
    except ImportError:
        from vocal_align import get_cached_vocals_path

    target = get_cached_vocals_path(audio_path) or audio_path
    key = (os.path.abspath(target), os.path.getmtime(target))
    if key in _EMISSION_CACHE:
        return _EMISSION_CACHE[key]

    model, _ = _get_model()
    data = _load_audio(target)
    n = len(data)
    chunk = int(_CHUNK_S * SAMPLE_RATE) // _HOP * _HOP
    ctx = int(_CONTEXT_S * SAMPLE_RATE) // _HOP * _HOP
    pieces = []
    with torch.inference_mode():
        for s in range(0, n, chunk):
            core = min(chunk, n - s) // _HOP
            if core <= 0:
                break
            a, b = max(0, s - ctx), min(n, s + chunk + ctx)
            seg = torch.from_numpy(data[a:b]).unsqueeze(0)
            if seg.shape[1] < 2 * _HOP:
                seg = torch.nn.functional.pad(seg, (0, 2 * _HOP - seg.shape[1]))
            em, _ = model(seg)
            em = em[0, (s - a) // _HOP:(s - a) // _HOP + core]
            if em.shape[0] < core:
                em = torch.cat([em, em[-1:].expand(core - em.shape[0], -1)])
            pieces.append(em)
    emission = torch.cat(pieces) if pieces else torch.zeros(0, len(_DICT))

    _EMISSION_CACHE.clear()
    _EMISSION_CACHE[key] = emission
    return emission


def _segment_end_after(t: float, segments: List[Tuple[float, float]]) -> float:
    for s, e in segments:
        if s - 0.05 <= t <= e:
            return e
    return t


def _ctc_align_lyrics_inproc(
    lyrics_lines: List[str],
    audio_path: str,
    vocal_segments: Optional[List[Tuple[float, float]]] = None,
    min_confidence: float = MIN_CONFIDENCE,
) -> Optional[List[Dict[str, Any]]]:
    """
    Aligns every lyric word to the moment it is sung. Returns None when the model is unavailable
    or the lyrics clearly do not match the audio (caller should fall back to energy-based sync).
    """
    lines = [str(l).strip() for l in lyrics_lines]
    if not any(lines) or not audio_path or not os.path.exists(audio_path) or not is_available():
        return None

    import torch
    import torchaudio.functional as AF
    try:
        from backend.lyric_engine import tokenize_line_words, compute_weighted_word_timestamps
        from backend.vocal_align import get_cached_vocals_path, detect_vocal_segments
    except ImportError:
        from lyric_engine import tokenize_line_words, compute_weighted_word_timestamps
        from vocal_align import get_cached_vocals_path, detect_vocal_segments

    try:
        _, vocab = _get_model()
        emission = compute_emission(audio_path)
    except Exception as e:
        log.warning(f"[CTC Align] Acoustic model unavailable: {e}")
        return None

    T, C = emission.shape
    star = C
    line_words: List[List[str]] = []
    targets: List[int] = [star]
    # (line_idx, word_idx, first_target_idx, last_target_idx)
    word_slots: List[Tuple[int, int, int, int]] = []
    for li, line in enumerate(lines):
        words = tokenize_line_words(line) if line else []
        words = [w for w in words if w.strip()] or ([line] if line else [])
        line_words.append(words)
        lcode = _lang_code(line)
        for wi, w in enumerate(words):
            ids = _romanize(w, lcode, vocab)
            if ids:
                word_slots.append((li, wi, len(targets), len(targets) + len(ids) - 1))
                targets.extend(ids)
        targets.append(star)

    repeats = sum(1 for i in range(1, len(targets)) if targets[i] == targets[i - 1])
    if not word_slots or len(targets) + repeats > T:
        log.info("[CTC Align] Lyrics too long for audio or nothing to align")
        return None

    em = torch.cat([emission, torch.full((T, 1), _STAR_LOGP, dtype=emission.dtype)], dim=1)
    try:
        ali, scores = AF.forced_align(em.unsqueeze(0), torch.tensor([targets], dtype=torch.int32), blank=0)
    except Exception as e:
        log.warning(f"[CTC Align] Forced alignment failed: {e}")
        return None
    spans = AF.merge_tokens(ali[0], scores[0].exp(), blank=0)
    if len(spans) != len(targets):
        log.warning(f"[CTC Align] Token span mismatch ({len(spans)} vs {len(targets)})")
        return None

    timed: Dict[Tuple[int, int], Tuple[float, float, float]] = {}
    line_scores: Dict[int, List[float]] = {}
    for li, wi, a, b in word_slots:
        ws = spans[a:b + 1]
        timed[(li, wi)] = (ws[0].start * _FRAME_S, ws[-1].end * _FRAME_S, 0.0)
        line_scores.setdefault(li, []).extend(float(s.score) for s in ws)

    all_scores = [s for v in line_scores.values() for s in v]
    confidence = sum(all_scores) / max(1, len(all_scores))
    if confidence < min_confidence:
        log.info(f"[CTC Align] Low acoustic confidence {confidence:.2f}; lyrics may not match this audio")
        return None

    if vocal_segments is None:
        try:
            vocal_segments = detect_vocal_segments(audio_path)
        except Exception:
            vocal_segments = []
    sustain_cap = 3.0 if get_cached_vocals_path(audio_path) else 1.2

    # Raw word spans per line, interpolating words that have no romanizable letters
    raw_lines: List[List[List[float]]] = []
    for li, words in enumerate(line_words):
        known = [(wi, timed[(li, wi)]) for wi in range(len(words)) if (li, wi) in timed]
        if not known:
            raw_lines.append([])
            continue
        rows: List[List[float]] = []
        for wi in range(len(words)):
            if (li, wi) in timed:
                s, e, _ = timed[(li, wi)]
                rows.append([s, e])
            else:
                prev = max((k for k in known if k[0] < wi), default=None, key=lambda k: k[0])
                nxt = min((k for k in known if k[0] > wi), default=None, key=lambda k: k[0])
                s = prev[1][1] if prev else max(0.0, nxt[1][0] - 0.3)
                e = nxt[1][0] if nxt else s + 0.3
                rows.append([s, max(s + 0.04, e)])
        raw_lines.append(rows)

    starts = [r[0][0] if r else None for r in raw_lines]
    aligned: List[Dict[str, Any]] = []
    for li, (line, words, rows) in enumerate(zip(lines, line_words, raw_lines)):
        if not line:
            continue
        next_line_start = next((s for s in starts[li + 1:] if s is not None), None)
        if not rows:
            prev_end = aligned[-1]["end"] if aligned else 0.0
            ln_end = (next_line_start - 0.05) if next_line_start else prev_end + 2.0
            ln_start = prev_end + 0.05
            if ln_end - ln_start < 0.4:
                ln_end = ln_start + 0.4
            aligned.append({
                "line_id": len(aligned), "start": round(ln_start, 2), "end": round(ln_end, 2),
                "text": line, "confidence": 0.0,
                "words": compute_weighted_word_timestamps(words or [line], ln_start, ln_end),
            })
            continue

        out_words = []
        for wi, (s, e) in enumerate(rows):
            if wi + 1 < len(rows):
                nxt = rows[wi + 1][0]
                gap = nxt - e
                end = nxt if gap < 0.3 else min(nxt, max(e + 0.15, min(_segment_end_after(e, vocal_segments), e + sustain_cap)))
            else:
                limit = (next_line_start - 0.05) if next_line_start is not None else e + sustain_cap
                end = max(e + 0.25, min(_segment_end_after(e, vocal_segments), e + sustain_cap))
                end = min(end, limit)
            end = max(end, s + 0.04)
            out_words.append({"word": words[wi], "start": round(s, 2), "end": round(end, 2)})

        sc = line_scores.get(li, [])
        aligned.append({
            "line_id": len(aligned),
            "start": out_words[0]["start"],
            "end": out_words[-1]["end"],
            "text": line,
            "confidence": round(sum(sc) / max(1, len(sc)), 3),
            "words": out_words,
        })

    repaired = _repair_collapsed_lines(aligned, vocal_segments, audio_path)
    log.info(f"[CTC Align] ✅ Word-aligned {len(aligned)} lines to the singer (confidence {confidence:.2f}, "
             f"{repaired} unclear lines re-spaced on sung phrases)")
    return aligned


def _repair_collapsed_lines(
    aligned: List[Dict[str, Any]],
    vocal_segments: List[Tuple[float, float]],
    audio_path: str,
    low_conf: float = 0.1,
) -> int:
    """
    Where the acoustic model could not hear the words (low confidence and a squashed or stretched
    line), re-spaces that run of lines over the sung phrases between the confident neighbours.
    """
    try:
        from backend.vocal_align import _assign_lines_to_phrases, time_line_words, detect_vocal_onsets
    except ImportError:
        from vocal_align import _assign_lines_to_phrases, time_line_words, detect_vocal_onsets

    n = len(aligned)
    weights = [float(max(4, len(l["text"].replace(" ", "")))) for l in aligned]
    good = [(l["end"] - l["start"]) / w for l, w in zip(aligned, weights) if l["confidence"] >= 0.3]
    if n < 3 or len(good) < 3:
        return 0
    good.sort()
    sec_per_w = good[len(good) // 2]

    def collapsed(i: int) -> bool:
        l = aligned[i]
        ratio = (l["end"] - l["start"]) / (weights[i] * sec_per_w)
        return l["confidence"] < low_conf and (ratio < 0.6 or ratio > 1.6)

    onsets = None
    repaired = 0
    i = 0
    while i < n:
        if not collapsed(i):
            i += 1
            continue
        a, b = i, i + 1
        while a > 0 and aligned[a - 1]["confidence"] < low_conf:
            a -= 1
        while b < n and aligned[b]["confidence"] < low_conf:
            b += 1
        i = b
        lo = aligned[a - 1]["end"] + 0.05 if a > 0 else aligned[a]["start"]
        hi = aligned[b]["start"] - 0.05 if b < n else aligned[b - 1]["end"]
        if hi - lo < 0.6 * (b - a):
            continue

        phrases = [(max(s, lo), min(e, hi)) for s, e in vocal_segments if e > lo + 0.1 and s < hi - 0.1]
        k = b - a
        runs = _assign_lines_to_phrases(phrases, weights[a:b]) if len(phrases) >= k else None
        if runs:
            windows = [(phrases[q:p], phrases[q][0], phrases[p - 1][1] + 0.25) for q, p in runs]
        else:
            total_w = sum(weights[a:b])
            windows, t = [], lo
            for w in weights[a:b]:
                d = (hi - lo) * w / total_w
                windows.append((None, t, t + d - 0.05))
                t += d

        if onsets is None:
            try:
                onsets = detect_vocal_onsets(audio_path, vocal_segments)
            except Exception:
                onsets = []
        for off, (spans, s, e) in enumerate(windows):
            idx = a + off
            if off + 1 < len(windows):
                e = min(e, windows[off + 1][1] - 0.05)
            e = round(max(min(e, hi), s + 0.6), 2)
            s = round(s, 2)
            line = aligned[idx]
            line["start"], line["end"] = s, e
            line["words"] = time_line_words(line["text"], s, e, onsets=onsets, vocal_spans=spans)
            repaired += 1
    return repaired


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WORKER_TIMEOUT_S = 900.0


def ctc_align_lyrics(
    lyrics_lines: List[str],
    audio_path: str,
    vocal_segments: Optional[List[Tuple[float, float]]] = None,
    min_confidence: float = MIN_CONFIDENCE,
) -> Optional[List[Dict[str, Any]]]:
    """
    Word-level sync for the studio, run in a throwaway process.

    Loading the wav2vec2 checkpoint right after Demucs has used the GPU faults inside
    torch's file reader on Windows (measured: 4/4 native access violations, exit 139).
    A fault cannot be caught from Python, so the aligner runs out-of-process and any
    failure simply means "no word alignment" and the caller keeps its acoustic sync.
    """
    lines = [str(l).strip() for l in lyrics_lines]
    if not any(lines) or not audio_path or not os.path.exists(audio_path):
        return None
    missing = missing_dependency()
    if missing:
        log.warning(
            f"[CTC Align] '{missing}' is not installed for {sys.executable}, so word timing is off. "
            f"Start VIDA with run_vida_desktop.bat to run the studio on the project venv."
        )
        return None

    import json
    import subprocess
    import tempfile

    job = {
        "lyrics_lines": lines,
        "audio_path": audio_path,
        "vocal_segments": [list(s) for s in vocal_segments] if vocal_segments else None,
        "min_confidence": min_confidence,
    }
    fd, job_path = tempfile.mkstemp(prefix="vida_ctc_job_", suffix=".json")
    out_path = job_path.replace("vida_ctc_job_", "vida_ctc_res_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(job, handle)
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        # This machine sits near its commit limit during a sync, and torch faults instead of
        # raising when it cannot map the aligner checkpoint. Hand back anything this process
        # still holds, without importing torch just to look for it.
        import gc
        gc.collect()
        torch = sys.modules.get("torch")
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
        def _aligned_lines():
            for attempt in (1, 2):
                proc = subprocess.run(
                    [sys.executable, "-m", "backend.ctc_worker", job_path, out_path],
                    cwd=_REPO_ROOT, env=env, timeout=_WORKER_TIMEOUT_S,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace",
                )
                if proc.returncode == 0 and os.path.exists(out_path):
                    with open(out_path, encoding="utf-8") as handle:
                        return json.load(handle).get("lines")
                if os.path.exists(out_path):
                    os.remove(out_path)
                tail = " | ".join((proc.stderr or "").strip().splitlines()[-2:])
                log.warning(f"[CTC Align] aligner process exited {proc.returncode:#x} (attempt {attempt}): {tail}")
            return None

        try:
            aligned = run_locked(_aligned_lines)
        except TimeoutError as busy:
            log.warning(f"[CTC Align] {busy}; keeping acoustic sync")
            return None
        if aligned is None:
            log.warning("[CTC Align] word aligner unavailable on this machine; keeping acoustic sync")
        return aligned
    except Exception as e:
        log.warning(f"[CTC Align] aligner process failed: {e}")
        return None
    finally:
        for path in (job_path, out_path):
            try:
                os.remove(path)
            except OSError:
                pass
