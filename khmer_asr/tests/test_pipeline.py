"""
Phase 15 — Quality Testing
===========================
Automated test runner for the Khmer ASR pipeline.

For every song in tests/sample_songs/ that has:
    audio.mp3  +  expected.txt

This script:
  1. Runs the full pipeline (or loads existing output)
  2. Compares: expected lyrics vs. raw ASR vs. corrected (future)
  3. Calls evaluate.py to produce evaluation/report.json and report.txt

Split strategy: By whole song — never split mid-song segments across train/test.

Usage:
    python tests/test_pipeline.py
    python tests/test_pipeline.py --model tiny --skip-separation
    python tests/test_pipeline.py --reuse-existing   # skip pipeline, just evaluate
"""

import sys
import os
import subprocess
import argparse
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Paths
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
KHMER_ASR_DIR = os.path.dirname(TESTS_DIR)
SAMPLE_SONGS_DIR = os.path.join(TESTS_DIR, "sample_songs")
EVAL_DIR = os.path.join(KHMER_ASR_DIR, "evaluation")
PIPELINE_SCRIPT = os.path.join(KHMER_ASR_DIR, "pipeline.py")
EVALUATE_SCRIPT = os.path.join(EVAL_DIR, "evaluate.py")


def get_python() -> str:
    """Return path to the active Python interpreter."""
    venv_python = os.path.join(KHMER_ASR_DIR, "..", "venv", "Scripts", "python.exe")
    if os.path.isfile(venv_python):
        return os.path.abspath(venv_python)
    return sys.executable


def discover_songs() -> list[dict]:
    if not os.path.isdir(SAMPLE_SONGS_DIR):
        log.warning(f"No sample_songs directory found: {SAMPLE_SONGS_DIR}")
        return []

    songs = []
    for entry in sorted(os.listdir(SAMPLE_SONGS_DIR)):
        song_dir = os.path.join(SAMPLE_SONGS_DIR, entry)
        if not os.path.isdir(song_dir):
            continue

        expected = os.path.join(song_dir, "expected.txt")
        if not os.path.isfile(expected):
            continue

        audio = None
        for ext in [".mp3", ".wav", ".m4a", ".flac"]:
            candidate = os.path.join(song_dir, f"audio{ext}")
            if os.path.isfile(candidate):
                audio = candidate
                break

        songs.append({
            "name": entry,
            "dir": song_dir,
            "audio": audio,
            "expected": expected,
        })

    return songs


def run_pipeline_on_song(song: dict, args: argparse.Namespace) -> bool:
    """Run the pipeline CLI on a single song. Returns True on success."""
    python = get_python()

    output_dir = os.path.join(song["dir"], "output")

    if not song["audio"]:
        log.warning(f"  [{song['name']}] No audio file (audio.mp3/wav) — skipping pipeline")
        return False

    cmd = [
        python, PIPELINE_SCRIPT,
        "--input", song["audio"],
        "--output-dir", output_dir,
    ]

    if args.model:
        cmd += ["--model", args.model]
    if args.skip_separation:
        cmd.append("--skip-separation")
    if args.device:
        cmd += ["--device", args.device]
    if args.verbose:
        cmd.append("--verbose")

    log.info(f"  [{song['name']}] Running pipeline...")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        log.error(f"  [{song['name']}] Pipeline FAILED (exit {result.returncode})")
        return False

    # Move raw_transcription.json up to song dir for evaluate.py discovery
    raw_src = os.path.join(output_dir, Path(song["audio"]).stem, "raw_transcription.json")

    # Look in output/<song_stem>/
    stem = "".join(
        c if c.isalnum() or c in "-_." else "_"
        for c in Path(song["audio"]).stem
    )
    raw_src = os.path.join(output_dir, stem, "raw_transcription.json")
    raw_dst = os.path.join(song["dir"], "raw_transcription.json")

    if os.path.isfile(raw_src) and not os.path.isfile(raw_dst):
        import shutil
        shutil.copy2(raw_src, raw_dst)
        log.info(f"  [{song['name']}] Copied raw_transcription.json to song dir")

    return True


def print_comparison(song: dict) -> None:
    """Print a side-by-side comparison of expected vs. ASR for a song."""
    raw_json = os.path.join(song["dir"], "raw_transcription.json")
    if not os.path.isfile(raw_json):
        log.info(f"  [{song['name']}] No output yet — run pipeline first")
        return

    with open(song["expected"], "r", encoding="utf-8") as f:
        expected_lines = [ln.strip() for ln in f if ln.strip()]

    with open(raw_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    asr_lines = [s["text"].strip() for s in data.get("segments", []) if s.get("text", "").strip()]

    print(f"\n{'─'*70}")
    print(f"  Song: {song['name']}")
    print(f"{'─'*70}")
    print(f"  {'EXPECTED':35s}  │  ASR OUTPUT")
    print(f"  {'─'*35}  │  {'─'*30}")

    max_lines = max(len(expected_lines), len(asr_lines))
    for i in range(max_lines):
        exp = expected_lines[i] if i < len(expected_lines) else ""
        asr = asr_lines[i] if i < len(asr_lines) else ""
        # Truncate for display
        exp_d = exp[:33] + ".." if len(exp) > 35 else exp
        asr_d = asr[:33] + ".." if len(asr) > 35 else asr
        match = "✓" if exp.strip() == asr.strip() else " "
        print(f"  {exp_d:35s}  │  {asr_d}  {match}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    parser = argparse.ArgumentParser(description="Phase 15 — Pipeline quality test runner")
    parser.add_argument("--model", choices=["tiny", "base", "small", "medium", "large-v3"],
                        default="small")
    parser.add_argument("--skip-separation", action="store_true")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu")
    parser.add_argument("--reuse-existing", action="store_true",
                        help="Skip pipeline; evaluate existing outputs only")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    songs = discover_songs()

    if not songs:
        print(f"\nNo test songs found in: {SAMPLE_SONGS_DIR}")
        print("\nTo add a test song:")
        print(f"  mkdir tests\\sample_songs\\my_khmer_song")
        print(f"  copy my_song.mp3 tests\\sample_songs\\my_khmer_song\\audio.mp3")
        print(f"  # Create expected.txt with one lyric line per row")
        print(f"  python tests\\test_pipeline.py --model small --skip-separation")
        return

    print(f"\nFound {len(songs)} test song(s)")
    passed = 0
    failed = 0

    for song in songs:
        print(f"\n[Testing] {song['name']}")

        if not args.reuse_existing:
            success = run_pipeline_on_song(song, args)
            if success:
                passed += 1
            else:
                failed += 1
        else:
            passed += 1

        print_comparison(song)

    # Run evaluator
    print(f"\n{'='*55}")
    print("Running evaluation (CER / WER / Timestamp MAE)...")
    print(f"{'='*55}")

    python = get_python()
    subprocess.run([python, EVALUATE_SCRIPT, "--test-dir", SAMPLE_SONGS_DIR, "--output-dir", EVAL_DIR])

    print(f"\nTest summary: {passed} passed, {failed} failed / {len(songs)} total")


if __name__ == "__main__":
    main()
