"""
Dynamic Vocal-Aware Forced Alignment Engine for VIDA.

Detects where vocals actually exist in audio using harmonic separation & energy analysis,
then maps lyrics lines to real vocal phrase segments — so instrumental intros, guitar solos,
and inter-verse bridges are automatically respected.

Includes:
1. Automatic detection of isolated Demucs stems (pure vocal clarity)
2. Harmonic-Percussive Separation (HPSS) to strip drums/percussion on mixed tracks
3. True First Vocal Onset Detection (eliminates early lyric starts during intros)
4. Inter-phrase breath pause / valley detection
5. Instrumental gap preservation (lyrics never run across solos)
6. Syllable-aware word interpolation with Khmer tokenization
"""

import os
import re
import math
import logging
from typing import List, Dict, Any, Tuple, Optional

log = logging.getLogger(__name__)


def get_cached_vocals_path(audio_path: str) -> Optional[str]:
    """Checks if isolated vocals stem already exists in uploads/stems/."""
    if not audio_path:
        return None
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    # Check parent uploads/stems directory
    cur_dir = os.path.dirname(os.path.abspath(audio_path))
    uploads_dir = os.path.dirname(cur_dir) if os.path.basename(cur_dir) in ("audio", "video") else cur_dir
    stems_dir = os.path.join(uploads_dir, "stems")
    
    expected_vocals = os.path.join(stems_dir, f"{base_name}_vocals.wav")
    if os.path.isfile(expected_vocals) and os.path.getsize(expected_vocals) > 10000:
        return expected_vocals
    return None


_SIGNAL_CACHE: Dict[Tuple[str, float], Tuple[Any, int, float, bool]] = {}
_ONSET_CACHE: Dict[Tuple[str, float], List[float]] = {}


def _load_vocal_signal(audio_path: str) -> Tuple[Any, int, float, bool]:
    """Returns (mono vocal-focused signal @16kHz, sr, duration, is_isolated_stem), cached per file."""
    import numpy as np
    from scipy.signal import butter, sosfilt

    vocal_stem = get_cached_vocals_path(audio_path)
    is_isolated = vocal_stem is not None
    target_path = vocal_stem if is_isolated else audio_path
    key = (os.path.abspath(target_path), os.path.getmtime(target_path))
    if key in _SIGNAL_CACHE:
        return _SIGNAL_CACHE[key]

    try:
        from backend.audio_analyzer import decode_audio_to_numpy
    except ImportError:
        from audio_analyzer import decode_audio_to_numpy
    data, sr, duration = decode_audio_to_numpy(target_path, target_sr=16000)
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    data = data.astype(np.float32, copy=False)

    if not is_isolated:
        try:
            sos = butter(4, [280, 3400], btype='bandpass', fs=sr, output='sos')
            data = sosfilt(sos, data).astype(np.float32, copy=False)
        except Exception:
            pass

    if len(_SIGNAL_CACHE) >= 2:
        _SIGNAL_CACHE.clear()
    _SIGNAL_CACHE[key] = (data, sr, duration, is_isolated)
    return _SIGNAL_CACHE[key]


def detect_vocal_onsets(
    audio_path: str,
    vocal_segments: Optional[List[Tuple[float, float]]] = None
) -> List[float]:
    """
    Detects sung syllable onsets (seconds) using band-limited log spectral flux on the
    isolated vocal stem (or vocal-band filtered mix). Onsets outside detected vocal
    activity are discarded so drums/instrument hits don't count as singing.
    """
    if not audio_path or not os.path.exists(audio_path):
        return []
    try:
        import numpy as np
        from scipy.signal import find_peaks

        data, sr, _, _ = _load_vocal_signal(audio_path)
        stem = get_cached_vocals_path(audio_path) or audio_path
        key = (os.path.abspath(stem), os.path.getmtime(stem))
        if key in _ONSET_CACHE:
            onsets = _ONSET_CACHE[key]
        else:
            n_fft = 1024
            hop = int(sr * 0.01)
            if len(data) < n_fft * 2:
                return []
            frames = np.lib.stride_tricks.sliding_window_view(data, n_fft)[::hop]
            window = np.hanning(n_fft).astype(np.float32)
            lo_bin = int(150 * n_fft / sr)
            hi_bin = int(4000 * n_fft / sr)
            bands = []
            for c in range(0, len(frames), 2000):
                spec = np.abs(np.fft.rfft(frames[c:c + 2000] * window, axis=1))[:, lo_bin:hi_bin]
                bands.append(np.log1p(10.0 * spec).astype(np.float32))
            band = np.concatenate(bands, axis=0)

            flux = np.maximum(0.0, np.diff(band, axis=0)).sum(axis=1)
            flux = np.concatenate([[0.0], flux])
            flux = np.convolve(flux, np.ones(3) / 3.0, mode='same')
            norm = np.percentile(flux, 95)
            if norm <= 0:
                return []
            flux = flux / norm

            local_win = 25  # ±0.25s adaptive threshold
            local_mean = np.convolve(flux, np.ones(2 * local_win + 1) / (2 * local_win + 1), mode='same')
            threshold = np.maximum(local_mean * 1.15 + 0.06, 0.18)
            peaks, _ = find_peaks(flux, height=threshold, distance=8)
            onsets = [round((float(p) * hop + n_fft / 2) / sr, 3) for p in peaks]
            if len(_ONSET_CACHE) >= 4:
                _ONSET_CACHE.clear()
            _ONSET_CACHE[key] = onsets

        if vocal_segments is None:
            vocal_segments = detect_vocal_segments(audio_path)
        if not vocal_segments:
            return list(onsets)

        filtered = []
        seg_idx = 0
        for t in onsets:
            while seg_idx < len(vocal_segments) and vocal_segments[seg_idx][1] + 0.1 < t:
                seg_idx += 1
            if seg_idx >= len(vocal_segments):
                break
            s, e = vocal_segments[seg_idx]
            if s - 0.12 <= t <= e + 0.1:
                filtered.append(t)
        return filtered
    except Exception as e:
        log.warning(f"[Onset Engine] Notice: {e}")
        return []


def snap_words_to_onsets(
    words: List[Dict[str, Any]],
    line_start: float,
    line_end: float,
    onsets: List[float],
    max_shift: float = 0.45
) -> List[Dict[str, Any]]:
    """
    Moves each word's start onto the singer's nearest real syllable onset using an
    order-preserving DP (words never swap order, each onset used at most once).
    Unmatched words are re-interpolated between matched anchors, and word ends are
    chained to the next word's start so the karaoke sweep follows the voice.
    The first word stays pinned to the line start.
    """
    n = len(words)
    if n < 2 or not onsets or line_end <= line_start:
        return words

    import bisect
    expected = [float(w.get("start", line_start)) for w in words]
    avg_dur = (line_end - line_start) / n
    tol = max(0.08, min(max_shift, avg_dur * 0.6))

    lo_i = bisect.bisect_right(onsets, line_start + 0.06)
    hi_i = bisect.bisect_left(onsets, line_end - 0.08)
    cands = onsets[lo_i:hi_i]
    if not cands:
        return words

    m = len(cands)
    INF = float("inf")
    # D[i][j]: best cost placing words 1..i using the first j candidates
    D = [[0.0] * (m + 1) for _ in range(n)]
    back = [[0] * (m + 1) for _ in range(n)]
    for i in range(1, n):
        D[i][0] = D[i - 1][0] + tol
        back[i][0] = 1
        for j in range(1, m + 1):
            best, choice = D[i][j - 1], 0
            skip_word = D[i - 1][j] + tol
            if skip_word < best:
                best, choice = skip_word, 1
            dist = abs(cands[j - 1] - expected[i])
            if dist <= tol:
                match = D[i - 1][j - 1] + dist
                if match < best:
                    best, choice = match, 2
            D[i][j] = best
            back[i][j] = choice

    anchors: Dict[int, float] = {0: float(line_start)}
    i, j = n - 1, m
    while i > 0:
        choice = back[i][j]
        if choice == 2:
            anchors[i] = cands[j - 1]
            i -= 1
            j -= 1
        elif choice == 1:
            i -= 1
        else:
            j -= 1

    if len(anchors) == 1:
        return words

    expected_end = max(expected[-1] + 0.05, float(words[-1].get("end", line_end)))
    anchor_idx = sorted(anchors) + [n]
    anchor_val = dict(anchors)
    anchor_val[n] = float(line_end)
    exp_ext = expected + [expected_end]

    new_starts = [0.0] * n
    for a, b in zip(anchor_idx, anchor_idx[1:]):
        new_starts[a] = anchor_val[a]
        span_e = exp_ext[b] - exp_ext[a]
        span_n = anchor_val[b] - anchor_val[a]
        for k in range(a + 1, b):
            frac = (exp_ext[k] - exp_ext[a]) / span_e if span_e > 1e-6 else (k - a) / (b - a)
            new_starts[k] = anchor_val[a] + frac * span_n

    result = []
    for k, w in enumerate(words):
        st = round(new_starts[k], 2)
        et = round(new_starts[k + 1], 2) if k + 1 < n else round(float(line_end), 2)
        if k + 1 < n:
            orig_dur = float(w.get("end", expected[k + 1])) - expected[k]
            if expected[k + 1] - float(w.get("end", expected[k + 1])) > 0.15:
                et = min(et, round(st + max(0.1, orig_dur), 2))
        nw = dict(w)
        nw["start"] = st
        nw["end"] = max(round(st + 0.04, 2), et)
        result.append(nw)
    return result


def _word_text(w: Any) -> str:
    if isinstance(w, dict):
        return str(w.get("word", w.get("text", "")))
    return str(w)


def _weighted_words(texts: List[str], start: float, end: float) -> List[Dict[str, Any]]:
    try:
        from backend.lyric_engine import compute_weighted_word_timestamps
    except ImportError:
        try:
            from lyric_engine import compute_weighted_word_timestamps
        except ImportError:
            compute_weighted_word_timestamps = None
    if compute_weighted_word_timestamps is not None:
        return compute_weighted_word_timestamps(texts, start, end)
    return _interpolate_words_simple(" ".join(texts), start, end)


def _retime_words(
    words: List[Any],
    old_start: float,
    old_end: float,
    new_start: float,
    new_end: float
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Maps word timestamps onto a new line span. Real per-word timing (e.g. from Whisper)
    is preserved via an affine remap; otherwise syllable-weighted timing is generated.
    Returns (words, has_real_timing).
    """
    texts = [_word_text(w) for w in words]
    if not texts:
        return [], False

    real = len(words) >= 2 and all(
        isinstance(w, dict) and isinstance(w.get("start"), (int, float)) and isinstance(w.get("end"), (int, float))
        for w in words
    )
    if real:
        starts = [float(w["start"]) for w in words]
        real = (
            all(b > a for a, b in zip(starts, starts[1:]))
            and starts[0] >= old_start - 0.5
            and float(words[-1]["end"]) <= old_end + 0.5
        )
    if not real:
        return _weighted_words(texts, new_start, new_end), False

    src_s = float(words[0]["start"])
    src_e = max(src_s + 0.05, float(words[-1]["end"]))
    # Absolute ASR timing is trusted; only translate when the line moved substantially,
    # and only compress (never stretch) when it overflows the new span.
    offset = new_start - src_s if abs(new_start - src_s) > 0.3 else 0.0
    overflow = (src_e + offset) - new_end
    scale = (new_end - new_start) / max(1e-6, src_e + offset - new_start) if overflow > 0 else 1.0
    out = []
    prev_s = new_start - 0.04
    for k, (w, t) in enumerate(zip(words, texts)):
        ws = new_start + (float(w["start"]) + offset - new_start) * scale
        we = new_start + (float(w["end"]) + offset - new_start) * scale
        ws = new_start if k == 0 else min(max(ws, prev_s + 0.04), new_end - 0.04)
        we = min(max(we, ws + 0.04), new_end)
        prev_s = ws
        nw = dict(w)
        nw.pop("text", None)
        nw.update({"word": t, "start": round(ws, 2), "end": round(we, 2)})
        out.append(nw)
    out[-1]["end"] = round(new_end, 2)
    return out, True


def time_line_words(
    text: str,
    start: float,
    end: float,
    onsets: Optional[List[float]] = None,
    vocal_spans: Optional[List[Tuple[float, float]]] = None
) -> List[Dict[str, Any]]:
    """
    Builds word timestamps for a line. When vocal_spans (the sung phrases inside the line)
    are given, words are spread over sung time only so the sweep pauses during breaths.
    Word starts are then snapped onto real vocal onsets.
    """
    words = _interpolate_words_simple(text, start, end)
    if vocal_spans and len(vocal_spans) > 1 and len(words) > 1:
        spans = [(max(s, start), min(e, end)) for s, e in vocal_spans if min(e, end) > max(s, start)]
        sung = sum(e - s for s, e in spans)
        if spans and sung > 0.2:
            def to_audio(pt: float) -> float:
                acc = 0.0
                for s, e in spans:
                    if acc + (e - s) >= pt:
                        return s + (pt - acc)
                    acc += e - s
                return spans[-1][1]

            local = _weighted_words([w["word"] for w in words], 0.0, sung)
            for k, (w, lw) in enumerate(zip(words, local)):
                w["start"] = round(start if k == 0 else to_audio(lw["start"]), 2)
                w["end"] = round(to_audio(lw["end"] - 1e-6), 2)
            words[-1]["end"] = round(end, 2)
    if onsets:
        words = snap_words_to_onsets(words, start, end, onsets)
    return words


def detect_vocal_segments(
    audio_path: str,
    min_vocal_dur: float = 0.5,
    min_silence_dur: float = 0.4
) -> List[Tuple[float, float]]:
    """
    Dynamic Vocal Activity Detection (VAD) Engine.
    Analyzes audio waveform to detect where singing/vocals actually exist.
    Returns list of (start, end) tuples marking vocal segments.
    
    Features:
    - Auto-uses isolated vocal stem if available in uploads/stems/
    - On mixed audio, uses Harmonic-Percussive Separation (HPSS) to strip drums
    - Vocal bandpass (280-3400 Hz) focusing on human singing formants
    - Adaptive percentile-normalized dB thresholding
    """
    try:
        import numpy as np

        # Isolated stem if cached, else vocal-band (280-3400 Hz) filtered mix
        vocal_data, sr, duration, is_isolated = _load_vocal_signal(audio_path)

        # 3. Compute frame-level RMS energy (20ms hop, 50ms window) in pure NumPy
        hop = int(sr * 0.02)
        frame_size = int(sr * 0.05)
        n_frames = max(1, (len(vocal_data) - frame_size) // hop + 1)
        
        try:
            frames = np.lib.stride_tricks.sliding_window_view(vocal_data, frame_size)[::hop]
            rms = np.sqrt(np.mean(frames ** 2, axis=1))
        except Exception:
            rms = np.zeros(n_frames, dtype=np.float32)
            for i in range(n_frames):
                s_idx = i * hop
                frame = vocal_data[s_idx:s_idx + frame_size]
                rms[i] = np.sqrt(np.mean(frame ** 2))

        if len(rms) == 0 or np.max(rms) == 0:
            return [(0.0, round(duration, 2))]

        # Relative dB scale relative to 95th percentile (resilient to sudden volume spikes)
        p95 = np.percentile(rms, 95)
        if p95 <= 0:
            p95 = np.max(rms)
        db = 20 * np.log10(np.maximum(rms / (p95 + 1e-9), 1e-5))

        # Dual-threshold hysteresis Schmitt trigger:
        # High threshold triggers vocal onset with high certainty.
        # Low threshold sustains vocal activity across soft vowels, vibrato, and endings.
        high_th = -30.0 if is_isolated else -17.0
        low_th = -38.0 if is_isolated else -23.0

        is_active = np.zeros(len(db), dtype=bool)
        state_active = False
        for i in range(len(db)):
            val = db[i]
            if not state_active:
                if val >= high_th:
                    state_active = True
                    is_active[i] = True
            else:
                if val >= low_th:
                    is_active[i] = True
                else:
                    state_active = False

        # Smooth: fill micro-gaps (< 220ms) to keep syllables together
        gap_frames = int(0.22 / 0.02)
        for i in range(len(is_active)):
            if not is_active[i]:
                left = max(0, i - gap_frames)
                right = min(len(is_active), i + gap_frames)
                if np.any(is_active[left:i]) and np.any(is_active[i+1:right+1]):
                    is_active[i] = True

        # Extract contiguous segments
        segments = []
        in_vocal = False
        seg_start = 0.0
        for i in range(len(is_active)):
            t = i * 0.02
            if is_active[i] and not in_vocal:
                seg_start = t
                in_vocal = True
            elif not is_active[i] and in_vocal:
                seg_end = t
                if seg_end - seg_start >= min_vocal_dur:
                    segments.append((round(seg_start, 2), round(seg_end, 2)))
                in_vocal = False
        if in_vocal and (duration - seg_start >= min_vocal_dur):
            segments.append((round(seg_start, 2), round(duration, 2)))

        # Merge segments with silence < min_silence_dur
        merged = []
        for seg in segments:
            if merged and seg[0] - merged[-1][1] < min_silence_dur:
                merged[-1] = (merged[-1][0], seg[1])
            else:
                merged.append(seg)

        # Split overly large continuous segments (> 7s) at breath pauses / energy valleys
        final_segments = []
        for s, e in merged:
            seg_dur = e - s
            if seg_dur > 7.0:
                s_frame = int(s / 0.02)
                e_frame = min(int(e / 0.02), len(rms))
                seg_rms = rms[s_frame:e_frame]
                if len(seg_rms) > 50:
                    kernel = np.ones(5) / 5.0
                    smoothed = np.convolve(seg_rms, kernel, mode='same')
                    from scipy.signal import find_peaks
                    valleys, _ = find_peaks(-smoothed, distance=int(1.8 / 0.02), prominence=0.005)
                    if len(valleys) > 0:
                        split_pts = [s] + [round(s + v * 0.02, 2) for v in valleys] + [e]
                        for j in range(len(split_pts) - 1):
                            if split_pts[j+1] - split_pts[j] >= 0.8:
                                final_segments.append((split_pts[j], split_pts[j+1]))
                        continue
            final_segments.append((s, e))

        return final_segments

    except Exception as e:
        print(f"[VAD Engine] Notice: {e}")
        return []


def detect_first_vocal_onset(audio_path: str, vocal_segments: Optional[List[Tuple[float, float]]] = None) -> float:
    """
    Finds the exact timestamp when the singer begins singing the very first word.
    Guarantees lyrics will NOT start playing during the instrumental intro.
    Uses the start of the first vocal segment that is long enough to be actual singing
    (filters out short pre-vocal breaths/noise bursts < 0.3s).
    """
    if vocal_segments and len(vocal_segments) > 0:
        # Skip very short initial segments (breaths, mic noise) — require >= 0.3s of real vocal
        for seg in vocal_segments:
            if seg[1] - seg[0] >= 0.3:
                return seg[0]
        # Fallback to first segment if all are short
        return vocal_segments[0][0]
    return 0.0


def _interpolate_words_simple(text: str, start: float, end: float) -> List[Dict[str, Any]]:
    """
    Distributes word-level timestamps with syllable-weighted singing durations.
    Delegates to lyric_engine.compute_weighted_word_timestamps for a single
    source of truth on phonetic weight calculation.
    """
    try:
        from backend.lyric_engine import tokenize_line_words, clean_subtitle_text, compute_weighted_word_timestamps
    except ImportError:
        try:
            from lyric_engine import tokenize_line_words, clean_subtitle_text, compute_weighted_word_timestamps
        except ImportError:
            tokenize_line_words = lambda x: x.split()
            clean_subtitle_text = lambda x: x.strip()
            compute_weighted_word_timestamps = None

    clean = clean_subtitle_text(text)
    if not clean:
        return [{"word": text, "start": start, "end": end}]

    words = tokenize_line_words(clean)
    if not words:
        return [{"word": clean, "start": start, "end": end}]

    # Use the canonical weighted timestamp engine if available
    if compute_weighted_word_timestamps is not None:
        return compute_weighted_word_timestamps(words, start, end)

    # Minimal fallback: proportional by character length
    dur = max(0.1, end - start)
    total_len = sum(max(1, len(w)) for w in words)
    result = []
    t = start
    for w in words:
        w_dur = (max(1, len(w)) / total_len) * dur
        result.append({
            "word": w,
            "start": round(t, 2),
            "end": round(t + w_dur, 2)
        })
        t += w_dur
    return result


def _assign_lines_to_phrases(
    phrases: List[Tuple[float, float]],
    weights: List[float]
) -> Optional[List[Tuple[int, int]]]:
    """
    Globally assigns each lyric line a contiguous run of sung phrases [q, p) via DP, so
    every line starts exactly on a real vocal onset. Minimises relative deviation between
    each line's sung time and its syllable-weighted expectation, penalises long silences
    inside a line (lines never straddle instrumental breaks), and allows stray phrases
    (ad-libs, hums) to be left without lyrics at a cost. Returns None if not enough phrases.
    """
    P, K = len(phrases), len(weights)
    if K == 0 or P < K:
        return None

    durs = [e - s for s, e in phrases]
    total = sum(durs)
    W = sum(weights) or 1.0
    expected = [max(0.6, w / W * total) for w in weights]
    mean_exp = total / K

    dur_pre = [0.0]
    for d in durs:
        dur_pre.append(dur_pre[-1] + d)
    gap_pre = [0.0]
    for a in range(1, P):
        g = phrases[a][0] - phrases[a - 1][1]
        gap_pre.append(gap_pre[-1] + max(0.0, g - 0.6) ** 1.5)

    INF = float("inf")
    dp = [[INF] * (P + 1) for _ in range(K + 1)]
    back: List[List[Optional[int]]] = [[None] * (P + 1) for _ in range(K + 1)]
    dp[0][0] = 0.0
    max_run = 8
    for k in range(K + 1):
        for p in range(1, P + 1):
            skip = dp[k][p - 1] + 0.35 + 0.6 * durs[p - 1] / mean_exp
            if skip < dp[k][p]:
                dp[k][p] = skip
                back[k][p] = -1
            if k == 0:
                continue
            exp_k = expected[k - 1]
            for q in range(max(k - 1, p - max_run), p):
                prev = dp[k - 1][q]
                if prev == INF:
                    continue
                sung = dur_pre[p] - dur_pre[q]
                inner_gaps = gap_pre[p - 1] - gap_pre[q]
                cost = prev + ((sung - exp_k) / exp_k) ** 2 + 0.8 * inner_gaps
                if cost < dp[k][p]:
                    dp[k][p] = cost
                    back[k][p] = q

    if dp[K][P] == INF:
        return None

    runs: List[Tuple[int, int]] = []
    k, p = K, P
    while k > 0 or p > 0:
        q = back[k][p]
        if q is None:
            return None
        if q == -1:
            p -= 1
        else:
            runs.append((q, p))
            k, p = k - 1, q
    runs.reverse()
    return runs if len(runs) == K else None


def _ensure_vocal_stem(audio_path: str) -> None:
    """Isolates vocals with Demucs before alignment when a CUDA GPU is available (CPU is too slow)."""
    if not audio_path or not os.path.exists(audio_path) or get_cached_vocals_path(audio_path):
        return
    try:
        try:
            from backend.vocal_separator import separate_vocals_demucs, cuda_available, missing_dependency
        except ImportError:
            from vocal_separator import separate_vocals_demucs, cuda_available, missing_dependency
        if missing_dependency() or not cuda_available():
            return
        separate_vocals_demucs(audio_path, device="cuda")
    except Exception as e:
        log.info(f"[Force Align] Vocal stem unavailable, aligning on full mix: {e}")


def force_align_lyrics_to_audio(
    lyrics_lines: List[str],
    audio_path: str,
    duration: float = 0.0
) -> List[Dict[str, Any]]:
    """
    Intelligent Forced Alignment Engine — VIDA SuperSmart Sync.

    Maps human lyrics to actual singing acoustics in the audio:
    - Auto-detects Demucs isolated vocal stems if available
    - Strips drums/percussion using HPSS to prevent false intro detection
    - Bypasses instrumental intros, guitar solos, and inter-verse bridges
    - Detects natural breath pauses / energy valleys between lines
    - Anchors each lyric line to real acoustic singing onsets
    - Works on any song in any language (Khmer, Vietnamese, English, etc.)
    """
    if not lyrics_lines:
        return []

    import numpy as np

    # Auto-detect duration
    if duration <= 0.0:
        try:
            from backend.audio_analyzer import decode_audio_to_numpy
            _, _, duration = decode_audio_to_numpy(audio_path, target_sr=8000)
        except Exception:
            duration = 180.0

    # Step 1: Detect actual vocal segments in audio (isolated vocal stem gives far cleaner phrases)
    _ensure_vocal_stem(audio_path)
    vocal_segments = detect_vocal_segments(audio_path)

    # Step 1b: Letter-level CTC forced alignment on the singer's voice (preferred when available).
    try:
        from backend.ctc_align import ctc_align_lyrics, is_available as _ctc_available
    except ImportError:
        try:
            from ctc_align import ctc_align_lyrics, is_available as _ctc_available
        except ImportError:
            ctc_align_lyrics = None
            _ctc_available = lambda: False
    if ctc_align_lyrics and _ctc_available() and audio_path and os.path.exists(audio_path):
        try:
            ctc_aligned = ctc_align_lyrics(lyrics_lines, audio_path, vocal_segments=vocal_segments)
        except Exception as e:
            log.info(f"[Force Align] CTC aligner raised, falling back: {e}")
            ctc_aligned = None
        if ctc_aligned and len(ctc_aligned) >= max(2, len(lyrics_lines) // 2):
            return ctc_aligned

    # Fallback to proportional spacing if audio contains zero detected voice
    if not vocal_segments or len(vocal_segments) < 2:
        log.info(f"[Force Align] VAD found {len(vocal_segments)} segments, using fallback spacing")
        intro = min(15.0, max(4.0, duration * 0.07))
        outro = min(12.0, max(3.0, duration * 0.05))
        singing_dur = max(10.0, duration - intro - outro)
        lengths = [max(4, len(line.replace(" ", ""))) for line in lyrics_lines]
        total_len = sum(lengths)
        aligned = []
        t = intro
        for idx, (line, length) in enumerate(zip(lyrics_lines, lengths)):
            line_dur = max(2.0, (length / total_len) * singing_dur)
            aligned.append({
                "line_id": idx,
                "start": round(t, 2),
                "end": round(t + line_dur, 2),
                "text": line,
                "words": _interpolate_words_simple(line, round(t, 2), round(t + line_dur, 2))
            })
            t += line_dur
        return aligned

    first_onset = vocal_segments[0][0]
    total_vocal_duration = sum(e - s for s, e in vocal_segments)
    log.info(f"[Force Align] Detected {len(vocal_segments)} vocal phrases. First vocal onset: {first_onset:.2f}s, "
             f"Total vocal time: {total_vocal_duration:.1f}s / {duration:.1f}s")

    onsets = detect_vocal_onsets(audio_path, vocal_segments)
    line_weights = [float(max(4, len(l.replace(" ", "")))) for l in lyrics_lines]
    runs = _assign_lines_to_phrases(vocal_segments, line_weights)
    if runs:
        aligned = []
        for idx, (line, (q, p)) in enumerate(zip(lyrics_lines, runs)):
            spans = vocal_segments[q:p]
            start_t = spans[0][0]
            end_t = spans[-1][1] + 0.25
            if idx + 1 < len(runs):
                end_t = min(end_t, vocal_segments[runs[idx + 1][0]][0] - 0.05)
            end_t = max(end_t, start_t + 0.6)
            start_t, end_t = round(start_t, 2), round(min(end_t, duration), 2)
            aligned.append({
                "line_id": idx,
                "start": start_t,
                "end": end_t,
                "text": line,
                "words": time_line_words(line, start_t, end_t, onsets=onsets, vocal_spans=spans)
            })
        log.info(f"[Force Align] ✅ Phrase-DP aligned {len(aligned)} lines onto {len(vocal_segments)} sung phrases, "
                 f"{len(onsets)} syllable onsets.")
        return aligned

    # Step 2: Partition audio into major Singing Blocks separated by true instrumental solos (gap >= 7.5s)
    singing_blocks = []
    cur_block = []
    for seg in vocal_segments:
        if cur_block and (seg[0] - cur_block[-1][1] >= 7.5):
            singing_blocks.append(cur_block)
            cur_block = [seg]
        else:
            cur_block.append(seg)
    if cur_block:
        singing_blocks.append(cur_block)

    # Step 3: Assign lyric lines to singing blocks proportionally to block duration
    num_lines = len(lyrics_lines)
    num_blocks = len(singing_blocks)
    block_vocal_durs = [sum(e - s for s, e in blk) for blk in singing_blocks]
    total_block_dur = max(1.0, sum(block_vocal_durs))

    lines_per_block = []
    assigned_count = 0

    if num_lines <= num_blocks:
        # Few lines: place them in the initial blocks starting from Block 0
        lines_per_block = [[line] for line in lyrics_lines]
        while len(lines_per_block) < num_blocks:
            lines_per_block.append([])
    else:
        for b_idx, b_dur in enumerate(block_vocal_durs):
            if b_idx == num_blocks - 1:
                lines_per_block.append(lyrics_lines[assigned_count:])
            else:
                remaining_blocks = num_blocks - 1 - b_idx
                remaining_lines = num_lines - assigned_count
                ratio = b_dur / total_block_dur
                k = max(1, round(ratio * num_lines))
                # Ensure we leave at least 1 line for each remaining block if possible
                k = min(k, max(1, remaining_lines - remaining_blocks))
                lines_per_block.append(lyrics_lines[assigned_count:assigned_count + k])
                assigned_count += k

    # Step 4: Map lines within each singing block to acoustic phrase boundaries
    aligned = []
    line_id = 0

    for b_idx, (block, b_lines) in enumerate(zip(singing_blocks, lines_per_block)):
        if not b_lines:
            continue

        b_clean = [l.replace(" ", "") for l in b_lines]
        b_weights = [max(4, len(cl)) for cl in b_clean]
        b_total_w = sum(b_weights)

        total_p_dur = sum(pe - ps for ps, pe in block)

        def phrase_time_to_audio(pt: float) -> float:
            pt = max(0.0, min(pt, total_p_dur - 0.001))
            accum = 0.0
            for ps, pe in block:
                d = pe - ps
                if accum + d >= pt:
                    return ps + (pt - accum)
                accum += d
            return block[-1][1]

        cur_w = 0
        for l_idx, (line, weight) in enumerate(zip(b_lines, b_weights)):
            p_start = (cur_w / b_total_w) * total_p_dur
            cur_w += weight
            p_end = (cur_w / b_total_w) * total_p_dur

            start_t = float(phrase_time_to_audio(p_start))
            end_t = float(phrase_time_to_audio(p_end))

            # Proportional line duration clamping:
            # Long sustained phrases are scaled down rather than hard-chopped.
            # Short lines are padded to a readable minimum.
            line_dur = end_t - start_t
            if line_dur > 6.5:
                # Scale down proportionally: keep at least 65% of the acoustic
                # span but never exceed 6.0s so subtitles remain readable.
                end_t = start_t + min(6.0, max(3.5, line_dur * 0.65))
            elif line_dur < 1.5:
                end_t = start_t + 1.5

            # Prevent overlap with previous line
            if aligned and start_t < aligned[-1]["end"]:
                start_t = round(float(aligned[-1]["end"]) + 0.05, 2)
                end_t = max(end_t, round(start_t + 1.2, 2))

            # Guarantee start is never before first onset
            if start_t < first_onset:
                start_t = float(first_onset)
                end_t = max(end_t, round(start_t + 1.5, 2))

            words_data = _interpolate_words_simple(line, round(start_t, 2), round(end_t, 2))

            aligned.append({
                "line_id": line_id,
                "start": round(float(start_t), 2),
                "end": round(float(end_t), 2),
                "text": line,
                "words": words_data
            })
            line_id += 1

    # Second pass: Fine-tune every line's onset and cutoff to true vocal acoustic phrases
    if vocal_segments and len(vocal_segments) > 0:
        aligned = calibrate_lyrics_with_vocal_activity(aligned, vocal_segments=vocal_segments, audio_path=audio_path)

    log.info(f"[Force Align] ✅ Successfully aligned {len(aligned)} lines across {len(singing_blocks)} musical blocks.")
    return aligned


def calibrate_lyrics_with_vocal_activity(
    lyrics: List[Dict[str, Any]],
    vocal_segments: Optional[List[Tuple[float, float]]] = None,
    audio_path: Optional[str] = None,
    max_trailing_hold: float = 0.25
) -> List[Dict[str, Any]]:
    """
    Acoustically and linguistically bounds every lyric line with millisecond precision:
    1. Snaps line start times to true acoustic singing onsets (eliminates early display during intros and instrumental breaks).
    2. Dynamically calibrates line end times according to the singer's actual singing speed:
       - Fast singing: detects early acoustic vocal cutoff and releases cleanly without lingering into pauses.
       - Slow singing: tracks sustained notes and vibrato, holding the subtitle until vocal energy ends.
    3. Strictly monotonic and non-overlapping: guarantees smooth playback and 100% compliant SRT/CapCut export.
    4. Re-distributes word-level karaoke timestamps so sweeps match the real singer's tempo.
    """
    if not lyrics:
        return []

    # If vocal_segments not passed but audio_path provided, detect them
    if not vocal_segments and audio_path and os.path.exists(audio_path):
        try:
            vocal_segments = detect_vocal_segments(audio_path)
        except Exception as e:
            log.warning(f"[Vocal Calibration] Could not detect vocal segments: {e}")
            vocal_segments = None

    calibrated = []
    spans: List[Tuple[float, float]] = []
    real_timing: List[bool] = []
    prev_end = 0.0
    first_onset = detect_first_vocal_onset(audio_path or "", vocal_segments)
    onsets = detect_vocal_onsets(audio_path, vocal_segments) if audio_path else []

    # 0. Global Drift Pre-Compensation:
    # Only shift forward if lyrics mistakenly started at 0.0s during an instrumental intro (> 4s)
    shift_offset = 0.0
    if vocal_segments and len(vocal_segments) > 0 and lyrics:
        first_lyric_start = float(lyrics[0].get("start", lyrics[0].get("time", 0.0)))
        if first_lyric_start < 1.0 and first_onset > 4.0:
            shift_offset = first_onset - first_lyric_start

    for i, line in enumerate(lyrics):
        raw_s = float(line.get("start") if line.get("start") is not None else line.get("time", 0.0))
        raw_e = float(line.get("end") if line.get("end") is not None else line.get("endTime", raw_s + 3.0))
        orig_start = max(0.0, raw_s + shift_offset)
        orig_end = max(orig_start + 0.5, raw_e + shift_offset)
        text = str(line.get("text", "")).strip()
        words = line.get("words", [])
        num_words = max(1, len(words)) if words else max(1, len(text.split()))

        next_raw_s = float(lyrics[i + 1].get("start", lyrics[i + 1].get("time", raw_e + 3.0))) if i + 1 < len(lyrics) else raw_s + 8.0
        next_orig_start = max(orig_start + 0.5, next_raw_s + shift_offset)

        calibrated_start = orig_start

        # 1. Start Time Alignment: Snap to real acoustic singing onset
        if vocal_segments and len(vocal_segments) > 0:
            if i == 0:
                calibrated_start = max(orig_start, first_onset)

            # Adaptive search window: allows up to 2.0s search to catch fast/drifting phrases
            gap_to_next = max(0.8, next_orig_start - orig_start)
            search_window = min(2.2, max(0.6, gap_to_next * 0.45))

            min_valid_start = max(0.0, prev_end + 0.04) if i > 0 else 0.0
            search_start = max(min_valid_start, orig_start - search_window)
            search_end = min(orig_start + search_window, next_orig_start - 0.15)

            # Collect candidate vocal segment onsets within the search window
            candidate_segments = [
                seg for seg in vocal_segments
                if search_start <= seg[0] <= search_end
            ]

            if candidate_segments:
                best_seg = None
                best_score = float('inf')
                for seg in candidate_segments:
                    seg_dur = seg[1] - seg[0]
                    time_dist = abs(seg[0] - orig_start)
                    score = time_dist - min(seg_dur, 1.2) * 0.35
                    if score < best_score:
                        best_score = score
                        best_seg = seg
                calibrated_start = max(min_valid_start, best_seg[0])
            else:
                inside_seg = None
                for seg in vocal_segments:
                    if seg[0] <= orig_start <= seg[1]:
                        inside_seg = seg
                        break
                if inside_seg:
                    calibrated_start = max(min_valid_start, orig_start)
                else:
                    upcoming = [seg[0] for seg in vocal_segments if seg[0] > orig_start]
                    if upcoming and upcoming[0] - orig_start < 2.0:
                        calibrated_start = max(min_valid_start, upcoming[0])
                    else:
                        calibrated_start = max(min_valid_start, orig_start)
        else:
            calibrated_start = max(prev_end + 0.04, orig_start)

        if calibrated_start < prev_end + 0.04:
            calibrated_start = prev_end + 0.04

        # 2. End Time Calibration: Support fast singing tempo (down to 0.5s per line)
        min_readable_dur = max(0.5, min(3.5, num_words * 0.18 + 0.3))

        if vocal_segments and len(vocal_segments) > 0:
            phrase_segs = [
                seg for seg in vocal_segments
                if seg[1] > calibrated_start and seg[0] < next_orig_start - 0.08
            ]

            if phrase_segs:
                vocal_cutoff = phrase_segs[0][1]
                for k in range(len(phrase_segs) - 1):
                    cur_s = phrase_segs[k]
                    nxt_s = phrase_segs[k + 1]
                    gap = nxt_s[0] - cur_s[1]
                    if gap >= 0.4:
                        vocal_cutoff = cur_s[1]
                        break
                    else:
                        vocal_cutoff = nxt_s[1]

                max_bound = next_orig_start - 0.05 if i + 1 < len(lyrics) else calibrated_start + 8.0
                acoustic_end = round(vocal_cutoff + max_trailing_hold, 2)

                if acoustic_end >= calibrated_start + min_readable_dur:
                    calibrated_end = min(max_bound, acoustic_end)
                else:
                    calibrated_end = min(max_bound, calibrated_start + min_readable_dur)
            else:
                linguistic_dur = max(min_readable_dur, min(4.0, num_words * 0.35 + 0.5))
                max_bound = next_orig_start - 0.05 if i + 1 < len(lyrics) else calibrated_start + 8.0
                calibrated_end = min(max_bound, calibrated_start + linguistic_dur)
        else:
            linguistic_dur = max(min_readable_dur, min(4.0, num_words * 0.35 + 0.5))
            max_bound = next_orig_start - 0.05 if i + 1 < len(lyrics) else calibrated_start + 8.0
            calibrated_end = min(max_bound, max(calibrated_start + min_readable_dur, orig_end))

        if calibrated_end <= calibrated_start + 0.3:
            calibrated_end = calibrated_start + 0.6

        calibrated_start = round(calibrated_start, 2)
        calibrated_end = round(calibrated_end, 2)
        prev_end = calibrated_end

        # 3. Word-level karaoke timing: keep real per-word timing, else syllable-weighted
        if words and isinstance(words, list):
            recalculated_words, is_real = _retime_words(
                words, raw_s, raw_e, calibrated_start, calibrated_end
            )
        else:
            recalculated_words, is_real = [], False

        calibrated.append({
            "line_id": line.get("line_id", i),
            "start": calibrated_start,
            "end": calibrated_end,
            "text": text,
            "words": recalculated_words or words
        })
        spans.append((calibrated_start, calibrated_end))
        real_timing.append(is_real)

    # 4. Anti-Cascading Smoothing Pass:
    # If the singer started the next phrase quickly, TRIM the previous phrase's end
    # so that the fast singing line starts ON TIME rather than being pushed forward into the future!
    for j in range(1, len(calibrated)):
        prev_line = calibrated[j - 1]
        curr_line = calibrated[j]

        if curr_line["start"] < prev_line["end"] + 0.04:
            if curr_line["start"] >= prev_line["start"] + 0.4:
                prev_line["end"] = round(curr_line["start"] - 0.04, 2)
            else:
                curr_line["start"] = round(prev_line["end"] + 0.04, 2)

        if curr_line["end"] <= curr_line["start"] + 0.3:
            curr_line["end"] = round(curr_line["start"] + 0.6, 2)

    # 5. Re-fit words to final line spans and snap them onto the singer's syllable onsets
    for j, line in enumerate(calibrated):
        words = line.get("words") or []
        if not words or not isinstance(words[0], dict):
            continue
        old_s, old_e = spans[j]
        if (line["start"], line["end"]) != (old_s, old_e):
            words, _ = _retime_words(words, old_s, old_e, line["start"], line["end"])
        if onsets:
            words = snap_words_to_onsets(
                words, line["start"], line["end"], onsets,
                max_shift=0.2 if real_timing[j] else 0.45
            )
        line["words"] = words

    return calibrated
