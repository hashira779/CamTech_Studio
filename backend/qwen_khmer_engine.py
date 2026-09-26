"""
Qwen3-ASR Khmer Singing Transcription Engine for VIDA.
Specialized for Khmer language songs using 'seanghay/Qwen3-ASR-0.6B-Khmer'.
Pairs with Demucs vocal separation and Khmer syllable tokenization.
"""

import os
import gc
import re
import math
import logging
from typing import List, Dict, Any, Optional, Callable, Tuple
import numpy as np

# Import Khmer normalization and post-processing tools from lyric_engine
try:
    from backend.lyric_engine import (
        normalize_khmer_orthography,
        clean_subtitle_text,
        tokenize_line_words,
        double_check_lyrics,
        is_khmer_text
    )
except ImportError:
    from lyric_engine import (
        normalize_khmer_orthography,
        clean_subtitle_text,
        tokenize_line_words,
        double_check_lyrics,
        is_khmer_text
    )

log = logging.getLogger(__name__)


def detect_vocal_segments(
    audio_path: str,
    target_sr: int = 16000,
    top_db: float = 28.0,
    frame_length: int = 2048,
    hop_length: int = 512,
    min_segment_dur: float = 0.8,
    max_segment_dur: float = 8.0
) -> List[Tuple[float, float]]:
    """
    Detects vocal singing phrases using audio energy on isolated vocal stems.
    Returns list of (start_sec, end_sec) intervals.
    """
    try:
        import soundfile as sf
        data, sr = sf.read(audio_path, dtype='float32')
        if len(data.shape) > 1:
            data = data.mean(axis=1)  # Mono

        duration = len(data) / sr

        # Resample to 16kHz if needed
        if sr != target_sr:
            step = sr / target_sr
            new_len = int(len(data) / step)
            indices = np.minimum(np.arange(new_len) * step, len(data) - 1).astype(int)
            data = data[indices]
            sr = target_sr

        # Compute Root Mean Square (RMS) energy in windows
        frames = len(data) // hop_length
        rms = np.zeros(frames, dtype=np.float32)
        for i in range(frames):
            start = i * hop_length
            end = min(start + frame_length, len(data))
            chunk = data[start:end]
            if len(chunk) > 0:
                rms[i] = np.sqrt(np.mean(chunk**2))

        # Convert to dB relative to peak
        max_rms = np.max(rms) if len(rms) > 0 else 1e-6
        if max_rms == 0:
            max_rms = 1e-6
        db = 20 * np.log10(np.maximum(rms / max_rms, 1e-5))

        # Identify vocal activity frames
        is_speech = db > -top_db

        # Merge contiguous active frames into segments
        segments = []
        in_segment = False
        seg_start_sec = 0.0

        for i, active in enumerate(is_speech):
            t = (i * hop_length) / sr
            if active and not in_segment:
                in_segment = True
                seg_start_sec = max(0.0, t - 0.15)  # Pre-roll pad
            elif not active and in_segment:
                seg_end_sec = min(duration, t + 0.25)  # Trailing pad
                if (seg_end_sec - seg_start_sec) >= min_segment_dur:
                    # Break up very long continuous segments (> max_segment_dur)
                    cur_start = seg_start_sec
                    while (seg_end_sec - cur_start) > max_segment_dur:
                        segments.append((cur_start, cur_start + max_segment_dur))
                        cur_start += max_segment_dur
                    if (seg_end_sec - cur_start) >= min_segment_dur:
                        segments.append((cur_start, seg_end_sec))
                in_segment = False

        if in_segment and (duration - seg_start_sec) >= min_segment_dur:
            segments.append((seg_start_sec, duration))

        # Fallback if no segments found (e.g. extremely quiet audio)
        if not segments and duration > 2.0:
            chunk_size = 5.0
            t = 0.0
            while t < duration:
                segments.append((t, min(duration, t + chunk_size)))
                t += chunk_size

        return segments

    except Exception as e:
        print(f"[Qwen VAD] Error detecting vocal segments: {e}")
        # Default fixed 5-second chunking fallback
        try:
            import soundfile as sf
            info = sf.info(audio_path)
            dur = info.duration
        except Exception:
            dur = 180.0
        chunks = []
        t = 0.0
        while t < dur:
            chunks.append((t, min(dur, t + 5.0)))
            t += 5.0
        return chunks


class QwenKhmerTranscriber:
    """
    Automatic Speech Recognition for Khmer Songs using 'seanghay/Qwen3-ASR-0.6B-Khmer'.
    Integrates vocal segmenting, ASR inference, phonetic spell correction, and word timestamps.
    """

    def __init__(self, model_name: str = "seanghay/Qwen3-ASR-0.6B-Khmer", device: str = "auto"):
        self.model_name = model_name
        self.device = device
        self.model = None

    def _load_model(self, progress_callback: Optional[Callable[[int, str], None]] = None):
        if self.model is not None:
            return

        if progress_callback:
            progress_callback(42, f"Loading Qwen3-ASR-0.6B Khmer AI...")

        try:
            import torch
            from qwen_asr import Qwen3ASRModel

            dev = "cuda:0" if (torch.cuda.is_available() and self.device != "cpu") else "cpu"
            dtype = torch.float16 if dev != "cpu" else torch.float32

            print(f"[Qwen3-ASR] Loading {self.model_name} on {dev} ({dtype})...")
            self.model = Qwen3ASRModel.from_pretrained(
                self.model_name,
                dtype=dtype,
                device_map=dev
            )
            if progress_callback:
                progress_callback(50, "Qwen3-ASR Khmer model ready!")
        except Exception as e:
            print(f"[Qwen3-ASR] Error loading model: {e}")
            raise RuntimeError(
                f"Could not load Qwen3-ASR Khmer model: {e}\n"
                f"Ensure 'pip install qwen-asr torch' is installed."
            )

    def transcribe(
        self,
        audio_path: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Transcribes vocal audio using Qwen3-ASR-0.6B-Khmer into timestamped, word-synced lyrics.
        """
        self._load_model(progress_callback=progress_callback)

        if progress_callback:
            progress_callback(52, "Detecting singing vocal phrases...")

        import soundfile as sf
        import tempfile

        audio_data, sr = sf.read(audio_path, dtype='float32')
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)

        segments = detect_vocal_segments(audio_path)
        total_segs = len(segments)
        lyrics = []

        if total_segs == 0:
            return lyrics

        temp_dir = tempfile.mkdtemp(prefix="vida_qwen_")

        try:
            for idx, (start_sec, end_sec) in enumerate(segments):
                if progress_callback:
                    pct = int(52 + (idx / total_segs) * 36)
                    progress_callback(pct, f"Transcribing phrase {idx+1}/{total_segs} (Qwen3 AI)")

                start_idx = int(start_sec * sr)
                end_idx = min(len(audio_data), int(end_sec * sr))
                chunk = audio_data[start_idx:end_idx]

                if len(chunk) < int(sr * 0.4):  # Skip sub-second fragments
                    continue

                chunk_file = os.path.join(temp_dir, f"chunk_{idx}.wav")
                sf.write(chunk_file, chunk, sr)

                # Transcribe chunk with Qwen3-ASR
                try:
                    res = self.model.transcribe(audio=chunk_file)
                    raw_text = res[0].text.strip() if res and len(res) > 0 else ""
                except Exception as t_err:
                    print(f"[Qwen3-ASR] Error on chunk {idx}: {t_err}")
                    raw_text = ""
                finally:
                    if os.path.exists(chunk_file):
                        try:
                            os.remove(chunk_file)
                        except Exception:
                            pass

                if not raw_text or len(raw_text.strip()) == 0:
                    continue

                # Post-processing: normalize and clean text
                clean_text = clean_subtitle_text(raw_text)
                if not clean_text:
                    continue

                # Tokenize into word/syllable units
                words = tokenize_line_words(clean_text)
                if not words:
                    words = [clean_text]

                # Distribute timestamps proportionally across words
                dur = end_sec - start_sec
                total_chars = max(1, sum(len(w) for w in words))
                word_objs = []
                cur_t = start_sec

                for w in words:
                    w_dur = dur * (len(w) / total_chars)
                    word_objs.append({
                        "word": w,
                        "start": round(cur_t, 2),
                        "end": round(cur_t + w_dur, 2)
                    })
                    cur_t += w_dur

                lyrics.append({
                    "id": f"line_{len(lyrics)+1}",
                    "time": round(start_sec, 2),
                    "endTime": round(end_sec, 2),
                    "text": clean_text,
                    "words": word_objs
                })

        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

        if progress_callback:
            progress_callback(92, "Auto-verifying and correcting Khmer singing spelling...")

        # Step 4: Final double-check and auto-correct verification
        verified_lyrics, _ = double_check_lyrics(lyrics)
        if verified_lyrics:
            lyrics = verified_lyrics

        if progress_callback:
            progress_callback(98, "Finalizing synchronized teleprompter...")

        return lyrics
