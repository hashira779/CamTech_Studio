"""
Stage 3 — Khmer ASR Transcription with faster-whisper
Converts vocals.wav → raw_transcription.json → lyrics.txt / .lrc / .srt

Design principles enforced here:
• raw_transcription.json is ALWAYS saved first — never modified downstream
• Model is unloaded from RAM after transcription (call gc.collect())
• WHISPER_CONDITION_ON_PREV=False prevents hallucination loops in long songs
• VAD filter skips silence so Whisper doesn't generate phantom lyrics
• Word-level timestamps enabled for LRC/SRT karaoke sync
"""

import os
import gc
import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Core transcription
# ─────────────────────────────────────────────────────────────────────────────

def transcribe(
    audio_path: str,
    output_dir: str,
    model_size: str = "large-v3-turbo",
    device: str = "cpu",
    language: str = "km",
    compute_type: str = "int8",
    beam_size: int = 3,
    best_of: int = 1,
    temperature: float = 0.0,
    word_timestamps: bool = True,
    vad_filter: bool = True,
    condition_on_prev: bool = False,
    cpu_threads: int = 8,
    khmer_model_path: str = "",
    initial_prompt: Optional[str] = None,
    two_pass: bool = False,
    low_conf_threshold: float = -1.5,
    repass_beam_size: int = 10,
    post_process: bool = True,
    segment_with_spaces: bool = False,
) -> dict:
    """
    Transcribe an audio file to Khmer lyrics using faster-whisper.

    Args:
        audio_path:          Input WAV/MP3 (vocals.wav recommended)
        output_dir:          Directory to save all output files
        model_size:          Whisper model size (tiny/base/small/medium/large-v3/large-v3-turbo)
        device:              "cpu" or "cuda"
        language:            ISO-639-1 language code ("km" = Khmer)
        compute_type:        Quantization — "int8" is fastest on CPU
        beam_size:           Beam search width (lower = faster)
        best_of:             Candidates per segment (1 = greedy)
        temperature:         0.0 = deterministic, no hallucination drift
        word_timestamps:     Enable word-level start/end times
        vad_filter:          Skip silence with Silero VAD
        condition_on_prev:   False = prevents repetition hallucinations
        cpu_threads:         Number of CPU threads for CTranslate2
        khmer_model_path:    Path/HF-repo of a fine-tuned Khmer model, or ""
        initial_prompt:      Khmer lyrics vocabulary prompt to bias decoder
        two_pass:            Re-transcribe low confidence segments with beam search
        low_conf_threshold:  avg_logprob threshold below which segments get re-transcribed
        repass_beam_size:    Beam search width for second pass
        post_process:        Run Stage 3.5 Khmer NLP post-processing & error correction
        segment_with_spaces: Format output with word-delimiting spaces

    Returns:
        dict with keys:
            raw_transcription_path: path to raw_transcription.json
            lyrics_txt:             path to lyrics.txt
            lyrics_lrc:             path to lyrics.lrc
            lyrics_srt:             path to lyrics.srt
            segments:               list of segment dicts
    """
    from faster_whisper import WhisperModel

    audio_path = str(audio_path)
    output_dir = str(output_dir)

    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    os.makedirs(output_dir, exist_ok=True)

    # Choose model source
    model_source = khmer_model_path if khmer_model_path else model_size
    log.info(f"[stage3] Loading model: '{model_source}' on {device} ({compute_type})")

    model = WhisperModel(
        model_source,
        device=device,
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        num_workers=1,
    )

    log.info(f"[stage3] Transcribing: {audio_path}")
    if initial_prompt:
        log.info(f"[stage3] Using initial_prompt ({len(initial_prompt)} chars) to bias Khmer lyrics decoding")

    # VAD parameters tuned for singing / Khmer music:
    # Lower threshold = more audio passes through (less aggressive filtering)
    vad_params = {
        "threshold": 0.3,              # default 0.5 — lower catches singing breath
        "min_speech_duration_ms": 100, # default 250 — catch short Khmer syllables
        "min_silence_duration_ms": 500,# default 2000 — tighter gaps in singing
        "speech_pad_ms": 400,          # pad around each detected speech region
    } if vad_filter else {}

    segments_iter, info = model.transcribe(
        audio_path,
        language=language if language != "auto" else None,
        beam_size=beam_size,
        best_of=best_of,
        temperature=temperature,
        word_timestamps=word_timestamps,
        vad_filter=vad_filter,
        vad_parameters=vad_params if vad_filter else None,
        condition_on_previous_text=condition_on_prev,
        initial_prompt=initial_prompt,
        no_speech_threshold=0.4,   # default 0.6 — singing often has lower confidence
        log_prob_threshold=-2.0,   # default -1.0 — allow lower-confidence Khmer segments
    )

    # Consume iterator — build structured segment list
    segments = []
    for seg in segments_iter:
        words = []
        if word_timestamps and seg.words:
            for w in seg.words:
                words.append({
                    "word": w.word,
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "probability": round(w.probability, 4),
                })

        segments.append({
            "id": seg.id,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": words,
            "avg_logprob": round(seg.avg_logprob, 4),
            "no_speech_prob": round(seg.no_speech_prob, 4),
            "compression_ratio": round(seg.compression_ratio, 4),
        })

    detected_language = info.language
    detected_prob = round(info.language_probability, 4)
    log.info(f"[stage3] Detected language: {detected_language} (prob={detected_prob})")
    log.info(f"[stage3] Pass 1 complete: {len(segments)} segments")

    # ── Optional Two-Pass Re-transcription for Low-Confidence Segments ──
    if two_pass and any(s["avg_logprob"] < low_conf_threshold for s in segments):
        try:
            from faster_whisper.audio import decode_audio
            log.info(f"[stage3] Running Pass 2 on low-confidence segments (avg_logprob < {low_conf_threshold})...")
            audio_waveform = decode_audio(audio_path, sampling_rate=16000)
            total_samples = len(audio_waveform)
            low_conf_count = 0
            improved_count = 0

            for seg in segments:
                if seg["avg_logprob"] < low_conf_threshold:
                    low_conf_count += 1
                    # Pad segment by 0.15s on each side to avoid clipping syllable onsets
                    start_sample = max(0, int((seg["start"] - 0.15) * 16000))
                    end_sample = min(total_samples, int((seg["end"] + 0.15) * 16000))
                    if end_sample - start_sample < 1600:
                        continue

                    slice_audio = audio_waveform[start_sample:end_sample]
                    slice_offset = start_sample / 16000.0

                    re_iter, _ = model.transcribe(
                        slice_audio,
                        language=language if language != "auto" else None,
                        beam_size=repass_beam_size,
                        best_of=repass_beam_size,
                        temperature=[0.0, 0.2, 0.4],
                        word_timestamps=word_timestamps,
                        vad_filter=False,
                        condition_on_previous_text=False,
                        initial_prompt=initial_prompt,
                    )
                    re_segs = list(re_iter)
                    if re_segs:
                        re_text = " ".join(s.text.strip() for s in re_segs).strip()
                        avg_lp = sum(s.avg_logprob for s in re_segs) / len(re_segs)
                        if re_text and avg_lp > seg["avg_logprob"]:
                            improved_count += 1
                            seg["text"] = re_text
                            seg["avg_logprob"] = round(avg_lp, 4)
                            if word_timestamps:
                                re_words = []
                                for rs in re_segs:
                                    if rs.words:
                                        for rw in rs.words:
                                            re_words.append({
                                                "word": rw.word,
                                                "start": round(slice_offset + rw.start, 3),
                                                "end": round(slice_offset + rw.end, 3),
                                                "probability": round(rw.probability, 4),
                                            })
                                if re_words:
                                    seg["words"] = re_words

            log.info(f"[stage3] Pass 2 finished: checked {low_conf_count} segments, improved {improved_count}")
        except Exception as e:
            log.warning(f"[stage3] Two-pass re-transcription encountered error: {e}")

    # ── Unload model immediately ──
    log.info("[stage3] Unloading Whisper model from RAM")
    del model
    gc.collect()

    # ── Stage 3.5: Khmer NLP Post-Processing ──
    if post_process:
        try:
            from stages.stage3_5_postprocess import post_process_segments
            log.info("[stage3] Applying Stage 3.5 Khmer NLP post-processing & corrections...")
            segments = post_process_segments(
                segments,
                segment_with_spaces=segment_with_spaces,
            )
        except Exception as e:
            log.warning(f"[stage3] Stage 3.5 post-processing encountered error: {e}")

    # ── Save raw transcription FIRST — never modify this file ──
    raw_path = os.path.join(output_dir, "raw_transcription.json")
    raw_data = {
        "model": model_source,
        "device": device,
        "language_hint": language,
        "detected_language": detected_language,
        "detected_language_probability": detected_prob,
        "initial_prompt_used": bool(initial_prompt),
        "two_pass_applied": two_pass,
        "post_process_applied": post_process,
        "audio_path": audio_path,
        "duration_seconds": round(info.duration, 2),
        "segments": segments,
    }
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)
    log.info(f"[stage3] Saved raw transcription: {raw_path}")

    # ── Generate lyrics.txt ──
    lyrics_txt_path = os.path.join(output_dir, "lyrics.txt")
    _save_lyrics_txt(segments, lyrics_txt_path)

    # ── Generate lyrics.lrc ──
    lyrics_lrc_path = os.path.join(output_dir, "lyrics.lrc")
    _save_lyrics_lrc(segments, lyrics_lrc_path)

    # ── Generate lyrics.srt ──
    lyrics_srt_path = os.path.join(output_dir, "lyrics.srt")
    _save_lyrics_srt(segments, lyrics_srt_path)

    return {
        "raw_transcription_path": raw_path,
        "lyrics_txt": lyrics_txt_path,
        "lyrics_lrc": lyrics_lrc_path,
        "lyrics_srt": lyrics_srt_path,
        "segments": segments,
        "detected_language": detected_language,
        "detected_language_probability": detected_prob,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Output formatters
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_lrc_time(seconds: float) -> str:
    """Format seconds as LRC timestamp [mm:ss.xx]"""
    mm = int(seconds // 60)
    ss = seconds % 60
    return f"[{mm:02d}:{ss:05.2f}]"


def _fmt_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm"""
    hh = int(seconds // 3600)
    mm = int((seconds % 3600) // 60)
    ss = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def _save_lyrics_txt(segments: list, path: str) -> None:
    """Plain text — one line per segment."""
    lines = []
    for seg in segments:
        text = seg["text"].strip()
        if text:
            lines.append(text)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    log.info(f"[stage3] Saved lyrics.txt: {path}")


def _save_lyrics_lrc(segments: list, path: str) -> None:
    """
    Standard LRC format with timestamps.
    Uses word-level timestamps when available for per-word karaoke tags.
    Falls back to segment-level timestamps.
    """
    lines = []
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue

        # If we have word-level timestamps, build enhanced LRC with <word> tags
        if seg.get("words"):
            ts = _fmt_lrc_time(seg["start"])
            # Build line with individual word timing
            word_parts = []
            for w in seg["words"]:
                wt = _fmt_lrc_time(w["start"])
                word_parts.append(f"{wt}{w['word']}")
            lines.append(f"{ts}" + "".join(w["word"] for w in seg["words"]))
        else:
            ts = _fmt_lrc_time(seg["start"])
            lines.append(f"{ts}{text}")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    log.info(f"[stage3] Saved lyrics.lrc: {path}")


def _save_lyrics_srt(segments: list, path: str) -> None:
    """Standard SRT subtitle format."""
    blocks = []
    for i, seg in enumerate(segments, start=1):
        text = seg["text"].strip()
        if not text:
            continue
        start_ts = _fmt_srt_time(seg["start"])
        end_ts = _fmt_srt_time(seg["end"])
        blocks.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks))
    log.info(f"[stage3] Saved lyrics.srt: {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Reload from saved JSON (no re-inference needed)
# ─────────────────────────────────────────────────────────────────────────────

def regenerate_from_raw(
    raw_json_path: str,
    output_dir: str,
    post_process: bool = False,
    segment_with_spaces: bool = False,
) -> None:
    """
    Re-generate lyrics.txt / .lrc / .srt from an existing raw_transcription.json
    without running Whisper again. Useful after manual corrections or to apply post-processing.
    """
    with open(raw_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data.get("segments", [])
    if post_process:
        from stages.stage3_5_postprocess import post_process_segments
        segments = post_process_segments(segments, segment_with_spaces=segment_with_spaces)

    _save_lyrics_txt(segments, os.path.join(output_dir, "lyrics.txt"))
    _save_lyrics_lrc(segments, os.path.join(output_dir, "lyrics.lrc"))
    _save_lyrics_srt(segments, os.path.join(output_dir, "lyrics.srt"))
    log.info(f"[stage3] Regenerated lyrics from {raw_json_path}")

