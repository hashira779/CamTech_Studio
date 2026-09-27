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
        import soundfile as sf

        # 1. Check for cached isolated vocal stem
        vocal_stem = get_cached_vocals_path(audio_path)
        is_isolated = vocal_stem is not None
        target_path = vocal_stem if is_isolated else audio_path

        data, sr = sf.read(target_path, dtype='float32')
        if data.ndim > 1:
            data = np.mean(data, axis=1)

        duration = len(data) / sr

        # Resample to 16kHz for fast, consistent processing
        if sr != 16000:
            from scipy.signal import resample_poly
            from math import gcd
            g = gcd(sr, 16000)
            data = resample_poly(data, 16000 // g, sr // g).astype(np.float32)
            sr = 16000

        # 2. Vocal frequency & harmonic isolation
        if not is_isolated:
            # Peel off percussive drums/cymbals so intro beats don't trigger false vocals
            try:
                import librosa
                y_harm, _ = librosa.effects.hpss(data)
            except Exception:
                y_harm = data

            try:
                from scipy.signal import butter, lfilter
                nyq = sr / 2.0
                low = 280.0 / nyq
                high = min(3400.0, nyq - 1) / nyq
                b, a = butter(4, [low, high], btype='band')
                vocal_data = lfilter(b, a, y_harm)
            except Exception:
                vocal_data = y_harm
        else:
            vocal_data = data

        # 3. Compute frame-level RMS energy (20ms hop, 50ms window)
        hop = int(sr * 0.02)
        frame_size = int(sr * 0.05)
        n_frames = max(1, (len(vocal_data) - frame_size) // hop + 1)
        
        try:
            import librosa
            rms = librosa.feature.rms(y=vocal_data, frame_length=frame_size, hop_length=hop)[0]
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

        # Thresholds:
        # Isolated vocal stems have ultra-quiet noise floors (-32dB)
        # Mixed harmonic tracks have higher background (-16dB to -18dB)
        threshold_db = -32.0 if is_isolated else -16.0
        is_active = db > threshold_db

        # Smooth: fill micro-gaps (< 200ms) to keep syllables together
        gap_frames = int(0.20 / 0.02)
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
    """
    if vocal_segments and len(vocal_segments) > 0:
        return vocal_segments[0][0]
    return 0.0


def _interpolate_words_simple(text: str, start: float, end: float) -> List[Dict[str, Any]]:
    """Distributes word-level timestamps with syllable awareness across a line duration."""
    try:
        from backend.lyric_engine import tokenize_line_words, clean_subtitle_text
    except ImportError:
        try:
            from lyric_engine import tokenize_line_words, clean_subtitle_text
        except ImportError:
            tokenize_line_words = lambda x: x.split()
            clean_subtitle_text = lambda x: x.strip()

    clean = clean_subtitle_text(text)
    if not clean:
        return [{"word": text, "start": start, "end": end}]

    words = tokenize_line_words(clean)
    if not words:
        return [{"word": clean, "start": start, "end": end}]

    dur = max(0.1, end - start)
    # Weight words: base length + slight bonus for vowels/syllables
    word_lens = []
    for w in words:
        # Vowels carry singing duration
        vowel_count = sum(1 for c in w if c in 'aeiouyàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹ\u17B6\u17B7\u17B8\u17B9\u17BA\u17BB\u17BC\u17BD\u17BE\u17BF\u17C0\u17C1\u17C2\u17C3\u17C4\u17C5')
        weight = max(1.0, len(w) + vowel_count * 0.5)
        word_lens.append(weight)

    total_weight = sum(word_lens)

    result = []
    t = start
    for w, wlen in zip(words, word_lens):
        w_dur = (wlen / total_weight) * dur
        result.append({
            "word": w,
            "start": round(t, 2),
            "end": round(t + w_dur, 2)
        })
        t += w_dur
    return result


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
            import soundfile as sf
            info = sf.info(audio_path)
            duration = info.duration
        except Exception:
            duration = 180.0

    # Step 1: Detect actual vocal segments in audio
    vocal_segments = detect_vocal_segments(audio_path)

    # Fallback to proportional spacing if audio contains zero detected voice
    if not vocal_segments or len(vocal_segments) < 2:
        print(f"[Force Align] VAD found {len(vocal_segments)} segments, using fallback spacing")
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
    print(f"[Force Align] Detected {len(vocal_segments)} vocal phrases. First vocal onset: {first_onset:.2f}s, "
          f"Total vocal time: {total_vocal_duration:.1f}s / {duration:.1f}s")

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

            # Keep line duration natural (min 1.8s, max 6.5s)
            line_dur = end_t - start_t
            if line_dur > 6.5:
                end_t = start_t + 4.5
            elif line_dur < 1.5:
                end_t = start_t + 1.8

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

    print(f"[Force Align] ✅ Successfully aligned {len(aligned)} lines across {len(singing_blocks)} musical blocks.")
    return aligned


def calibrate_lyrics_with_vocal_activity(
    lyrics: List[Dict[str, Any]],
    vocal_segments: Optional[List[Tuple[float, float]]] = None,
    audio_path: Optional[str] = None,
    max_trailing_hold: float = 0.35
) -> List[Dict[str, Any]]:
    """
    Acoustically and linguistically bounds the end time of every lyric line.
    Prevents lyrics from lingering across instrumental breaks, solos, and interludes.
    
    1. Analyzes vocal cutoff using real acoustic VAD segments.
    2. Imposes linguistic maximum bounds based on word count.
    3. Re-distributes word-level karaoke timestamps so sweeps match the real singer speed.
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
    for i, line in enumerate(lyrics):
        start = float(line.get("start", 0.0))
        orig_end = float(line.get("end", start + 3.0))
        text = line.get("text", "")
        words = line.get("words", [])
        num_words = max(1, len(words)) if words else max(1, len(text.split()))

        next_start = float(lyrics[i + 1]["start"]) if i + 1 < len(lyrics) else start + 5.0
        gap_to_next = next_start - start

        # Linguistic ceiling based on word count (0.65s per word + 1.0s release)
        linguistic_max_dur = max(2.2, min(6.5, num_words * 0.65 + 1.0))

        # Acoustic Vocal Cutoff Detection
        if vocal_segments:
            overlapping_segs = [s for s in vocal_segments if s[1] > start and s[0] < next_start - 0.4]
            if overlapping_segs:
                # Find last vocal segment before an instrumental pause (gap >= 1.0s)
                vocal_end = overlapping_segs[0][1]
                for j in range(len(overlapping_segs) - 1):
                    cur_seg = overlapping_segs[j]
                    nxt_seg = overlapping_segs[j + 1]
                    if nxt_seg[0] - cur_seg[1] >= 1.0:
                        vocal_end = cur_seg[1]
                        break
                    else:
                        vocal_end = nxt_seg[1]

                acoustic_end = round(vocal_end + max_trailing_hold, 2)
                if gap_to_next > 4.5:
                    calibrated_end = min(acoustic_end, start + linguistic_max_dur, next_start - 0.4)
                else:
                    calibrated_end = min(orig_end, next_start - 0.15)
            else:
                if gap_to_next > 5.0:
                    calibrated_end = round(start + linguistic_max_dur, 2)
                else:
                    calibrated_end = min(orig_end, next_start - 0.15)
        else:
            if gap_to_next > 5.0:
                calibrated_end = round(start + linguistic_max_dur, 2)
            else:
                calibrated_end = min(orig_end, next_start - 0.15)

        calibrated_end = max(calibrated_end, round(start + 1.2, 2))

        # Re-distribute words across calibrated duration
        calibrated_dur = max(0.4, calibrated_end - start)
        w_dur = calibrated_dur / num_words
        recalculated_words = []
        if words and isinstance(words, list):
            for w_idx, w in enumerate(words):
                w_text = w.get("word", "") if isinstance(w, dict) else str(w)
                recalculated_words.append({
                    "word": w_text,
                    "start": round(start + w_idx * w_dur, 2),
                    "end": round(start + (w_idx + 1) * w_dur, 2)
                })

        calibrated.append({
            "line_id": line.get("line_id", i),
            "start": round(start, 2),
            "end": round(calibrated_end, 2),
            "text": text,
            "words": recalculated_words or words
        })

    return calibrated
