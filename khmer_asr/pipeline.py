#!/usr/bin/env python3
"""
Khmer Singing Lyrics Pipeline — Main CLI Entry Point
=====================================================

Usage:
    python pipeline.py --input song.mp3 [OPTIONS]

Examples:
    # Full pipeline (separation + transcription)
    python pipeline.py --input uploads/my_song.mp3

    # Transcribe directly from YouTube URL
    python pipeline.py --url "https://www.youtube.com/watch?v=XXXXXXXXXXX"

    # YouTube URL + skip separation (faster)
    python pipeline.py --url "https://youtu.be/XXXXXXXXXXX" --skip-separation

    # Skip vocal separation (use raw audio directly)
    python pipeline.py --input uploads/vocals_only.wav --skip-separation

    # Use medium model for better Khmer accuracy
    python pipeline.py --input uploads/my_song.mp3 --model medium

    # CPU with 4 threads (lower RAM usage)
    python pipeline.py --input uploads/my_song.mp3 --cpu-threads 4

    # Regenerate LRC/SRT from existing raw JSON (no re-inference)
    python pipeline.py --regen output/my_song/raw_transcription.json

Pipeline stages:
    0. yt-dlp  → download from YouTube URL  (only when --url is used)
    1. FFmpeg  → 16kHz mono WAV
    2. Demucs  → vocals.wav  (can be skipped with --skip-separation)
    3. Whisper → raw_transcription.json → lyrics.txt / .lrc / .srt
"""

import sys
import os
import argparse
import logging
import time
from pathlib import Path

# ── ensure khmer_asr directory is on sys.path ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from stages.stage0_download import is_youtube_url, download_audio, get_video_info
from stages.stage1_convert import convert_to_wav, probe_duration
from stages.stage3_transcribe import transcribe, regenerate_from_raw


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s  %(levelname)-7s  %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")


def build_output_dir(input_path: str, base_output_dir: str) -> str:
    """Creates a per-song output directory under base_output_dir."""
    song_name = Path(input_path).stem
    # Sanitize: replace spaces and problematic chars
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in song_name)
    out = os.path.join(base_output_dir, safe_name)
    os.makedirs(out, exist_ok=True)
    return out


def run_pipeline(args: argparse.Namespace) -> int:
    """
    Execute the pipeline and return exit code (0 = success).
    """
    log = logging.getLogger(__name__)

    # ──────────────────────────────────────────
    # STAGE 0 — YouTube Download (if --url used)
    # ──────────────────────────────────────────
    if args.url:
        url = args.url.strip()
        log.info("=" * 55)
        log.info("STAGE 0 — YouTube Download (yt-dlp)")
        log.info("=" * 55)

        # Download to uploads/ so files persist
        dl_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
        os.makedirs(dl_dir, exist_ok=True)

        try:
            downloaded = download_audio(
                url=url,
                output_dir=dl_dir,
                audio_format="mp3",
            )
            input_path = downloaded
            log.info(f"Stage 0 done. Audio saved: {input_path}")
        except Exception as e:
            log.error(f"Stage 0 failed: {e}")
            return 1
    else:
        input_path = str(args.input)

    if not os.path.isfile(input_path):
        log.error(f"Input file not found: {input_path}")
        return 1

    output_dir = build_output_dir(input_path, args.output_dir)
    log.info(f"Output directory: {output_dir}")

    device = args.device if args.device else config.DEVICE
    model_size = args.model if args.model else config.WHISPER_MODEL
    cpu_threads = args.cpu_threads if args.cpu_threads else config.WHISPER_CPU_THREADS
    khmer_model = args.khmer_model if args.khmer_model else config.WHISPER_KHMER_MODEL

    total_start = time.time()

    # ──────────────────────────────────────────
    # STAGE 1 — Convert to 16kHz mono WAV
    # ──────────────────────────────────────────
    stage1_start = time.time()
    log.info("=" * 55)
    log.info("STAGE 1 — Audio Conversion (FFmpeg)")
    log.info("=" * 55)

    converted_wav = os.path.join(output_dir, "_converted_16k.wav")
    try:
        convert_to_wav(
            input_path=input_path,
            output_path=converted_wav,
            sample_rate=config.AUDIO_SAMPLE_RATE,
            channels=config.AUDIO_CHANNELS,
        )
    except Exception as e:
        log.error(f"Stage 1 failed: {e}")
        return 1

    duration = probe_duration(input_path)
    if duration > 0:
        log.info(f"Song duration: {duration:.1f}s ({duration/60:.1f} min)")
    log.info(f"Stage 1 done in {time.time() - stage1_start:.1f}s")

    # ──────────────────────────────────────────
    # STAGE 2 — Vocal Separation (Demucs)
    # ──────────────────────────────────────────
    if args.skip_separation:
        log.info("=" * 55)
        log.info("STAGE 2 — Vocal Separation SKIPPED (--skip-separation)")
        log.info("=" * 55)
        audio_for_transcription = converted_wav
    else:
        stage2_start = time.time()
        log.info("=" * 55)
        log.info("STAGE 2 — Vocal Separation (Demucs)")
        log.info("=" * 55)

        try:
            from stages.stage2_separate import separate_vocals_subprocess
            separation_result = separate_vocals_subprocess(
                wav_path=converted_wav,
                output_dir=output_dir,
                model_name=args.demucs_model or config.DEMUCS_MODEL,
                device=device,
                shifts=config.DEMUCS_SHIFTS,
                segment=config.DEMUCS_SEGMENT,
                overlap=config.DEMUCS_OVERLAP,
                delete_input_wav=config.DELETE_TEMP_WAV,
            )
            audio_for_transcription = separation_result["vocals"]
        except ImportError:
            log.warning("Demucs not installed — falling back to direct transcription.")
            log.warning("Install demucs: see install.bat or requirements.txt")
            audio_for_transcription = converted_wav
        except Exception as e:
            log.error(f"Stage 2 failed: {e}")
            log.info("Falling back to transcribing full mix (no separation)")
            audio_for_transcription = converted_wav

        log.info(f"Stage 2 done in {time.time() - stage2_start:.1f}s")

    # ──────────────────────────────────────────
    # STAGE 3 — Transcription (faster-whisper)
    # ──────────────────────────────────────────
    stage3_start = time.time()
    log.info("=" * 55)
    log.info(f"STAGE 3 — Transcription (model={model_size}, device={device})")
    log.info("=" * 55)

    try:
        use_two_pass = False if args.no_two_pass else config.WHISPER_TWO_PASS
        use_post_process = False if args.no_post_process else getattr(config, "KHMER_POSTPROCESS_ENABLED", True)
        prompt = args.initial_prompt if args.initial_prompt is not None else getattr(config, "WHISPER_INITIAL_PROMPT", None)

        result = transcribe(
            audio_path=audio_for_transcription,
            output_dir=output_dir,
            model_size=model_size,
            device=device,
            language=args.language or config.WHISPER_LANGUAGE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
            beam_size=config.WHISPER_BEAM_SIZE,
            best_of=config.WHISPER_BEST_OF,
            temperature=config.WHISPER_TEMPERATURE,
            word_timestamps=config.WHISPER_WORD_TIMESTAMPS,
            vad_filter=config.WHISPER_VAD_FILTER,
            condition_on_prev=config.WHISPER_CONDITION_ON_PREV,
            cpu_threads=cpu_threads,
            khmer_model_path=khmer_model,
            initial_prompt=prompt,
            two_pass=use_two_pass,
            low_conf_threshold=getattr(config, "WHISPER_LOW_CONF_THRESHOLD", -1.5),
            repass_beam_size=getattr(config, "WHISPER_REPASS_BEAM_SIZE", 10),
            post_process=use_post_process,
            segment_with_spaces=args.segment_spaces or getattr(config, "KHMER_SEGMENT_WITH_SPACES", False),
        )
    except Exception as e:
        log.error(f"Stage 3 failed: {e}")
        return 1

    log.info(f"Stage 3 done in {time.time() - stage3_start:.1f}s")

    # ── Clean up temporary converted WAV (if separation was used) ──
    if not args.skip_separation and config.DELETE_TEMP_WAV:
        if os.path.isfile(converted_wav):
            os.remove(converted_wav)
            log.info(f"Deleted temp file: {converted_wav}")

    # ──────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────
    total_time = time.time() - total_start
    n_segments = len(result["segments"])
    lang = result["detected_language"]
    lang_prob = result["detected_language_probability"]

    log.info("=" * 55)
    log.info("PIPELINE COMPLETE")
    log.info("=" * 55)
    log.info(f"  Total time:        {total_time:.1f}s ({total_time/60:.1f} min)")
    log.info(f"  Segments:          {n_segments}")
    log.info(f"  Detected language: {lang} (confidence={lang_prob:.0%})")
    log.info(f"  Output directory:  {output_dir}")
    log.info(f"  Files written:")
    log.info(f"    → {result['raw_transcription_path']}")
    log.info(f"    → {result['lyrics_txt']}")
    log.info(f"    → {result['lyrics_lrc']}")
    log.info(f"    → {result['lyrics_srt']}")

    # Preview first few lines
    if n_segments > 0:
        log.info("\n  Preview (first 5 lines):")
        for seg in result["segments"][:5]:
            ts = f"[{int(seg['start']//60):02d}:{seg['start']%60:05.2f}]"
            log.info(f"    {ts} {seg['text'].strip()}")

    return 0


def run_regen(raw_json_path: str, post_process: bool = True, segment_with_spaces: bool = False) -> int:
    """Regenerate output files from existing raw_transcription.json."""
    log = logging.getLogger(__name__)
    raw_json_path = str(raw_json_path)
    if not os.path.isfile(raw_json_path):
        log.error(f"File not found: {raw_json_path}")
        return 1
    output_dir = os.path.dirname(raw_json_path)
    log.info(f"Regenerating lyrics from: {raw_json_path} (post_process={post_process})")
    regenerate_from_raw(
        raw_json_path,
        output_dir,
        post_process=post_process,
        segment_with_spaces=segment_with_spaces,
    )
    log.info("Done.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Khmer Singing Lyrics Pipeline — yt-dlp → FFmpeg → Demucs → Whisper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Input — local file OR YouTube URL
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", "-i", metavar="FILE",
                       help="Input audio/video file (mp3, mp4, wav, flac, …)")
    group.add_argument("--url", "-u", metavar="YOUTUBE_URL",
                       help="YouTube URL — download audio then transcribe")
    group.add_argument("--regen", metavar="JSON",
                       help="Path to existing raw_transcription.json — regenerate outputs only")

    # Output
    parser.add_argument("--output-dir", "-o", default=config.OUTPUT_DIR, metavar="DIR",
                        help=f"Base output directory (default: {config.OUTPUT_DIR})")

    # Pipeline control
    parser.add_argument("--skip-separation", action="store_true",
                        help="Skip Demucs; transcribe the full audio directly")

    # Model selection
    parser.add_argument("--model", "-m",
                        choices=["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3", "large-v3-turbo", "turbo"],
                        default=None,
                        help=f"Whisper model size (default: {config.WHISPER_MODEL})")
    parser.add_argument("--khmer-model", metavar="PATH_OR_REPOID", default=None,
                        help="Custom fine-tuned Khmer Whisper model (HF repo-id or local path)")
    parser.add_argument("--demucs-model", default=None,
                        help=f"Demucs model name (default: {config.DEMUCS_MODEL})")

    # ASR tuning & Khmer enhancements
    parser.add_argument("--initial-prompt", default=None,
                        help="Initial prompt to bias decoding toward Khmer vocabulary")
    parser.add_argument("--no-two-pass", action="store_true",
                        help="Disable second pass beam search on low-confidence segments")
    parser.add_argument("--no-post-process", action="store_true",
                        help="Disable Stage 3.5 Khmer NLP post-processing and error corrections")
    parser.add_argument("--segment-spaces", action="store_true",
                        help="Format output Khmer lyrics with word boundary spaces using khmer-nltk")

    # Device / hardware
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default=None,
                        help=f"Device (default: {config.DEVICE})")
    parser.add_argument("--cpu-threads", type=int, default=None, metavar="N",
                        help=f"CPU threads for CTranslate2 (default: {config.WHISPER_CPU_THREADS})")

    # Language
    parser.add_argument("--language", "-l", default=None, metavar="CODE",
                        help=f"Force language code (default: {config.WHISPER_LANGUAGE} = Khmer). "
                             f"Use 'auto' to auto-detect.")

    # Verbose
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    if args.regen:
        sys.exit(run_regen(
            args.regen,
            post_process=not args.no_post_process,
            segment_with_spaces=args.segment_spaces,
        ))
    else:
        sys.exit(run_pipeline(args))



if __name__ == "__main__":
    main()
