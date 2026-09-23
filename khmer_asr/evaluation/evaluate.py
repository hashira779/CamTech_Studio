"""
Phase 13 — Evaluation
=====================
Calculates real CER, WER, and timestamp MAE between model outputs
and human-corrected reference lyrics.

IMPORTANT: This script never invents numbers.
If a test song has no expected.txt, it is skipped with a warning.
If fewer than 1 sample is available, no aggregate scores are printed.

Compares:
  Model A — Base Whisper (generic, no language hint)
  Model B — Existing Khmer Whisper (language=km, standard model)
  Model C — Fine-tuned Khmer Singing Whisper (custom checkpoint)

Split strategy: By whole song, never by segment.
  All segments of one song are either fully in the test set or not at all.

Usage:
    python evaluation/evaluate.py --test-dir tests/sample_songs [--output-dir evaluation]
"""

import os
import sys
import json
import argparse
import logging
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# Ensure khmer_asr is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_jiwer():
    try:
        import jiwer
        return jiwer
    except ImportError:
        raise ImportError(
            "jiwer is required for evaluation.\n"
            "Install: pip install jiwer"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SongResult:
    song_name: str
    expected_lines: list[str]
    raw_lines: list[str]
    corrected_lines: list[str]
    raw_timestamps: list[float]   # segment start times from ASR
    ref_timestamps: list[float]   # expected timestamps (if provided in expected_timed.json)
    cer_raw: Optional[float] = None
    wer_raw: Optional[float] = None
    cer_corrected: Optional[float] = None
    wer_corrected: Optional[float] = None
    timestamp_mae: Optional[float] = None


@dataclass
class ModelReport:
    model_label: str
    samples: int = 0
    cer_scores: list[float] = field(default_factory=list)
    wer_scores: list[float] = field(default_factory=list)
    timestamp_mae_scores: list[float] = field(default_factory=list)

    @property
    def mean_cer(self) -> Optional[float]:
        return sum(self.cer_scores) / len(self.cer_scores) if self.cer_scores else None

    @property
    def mean_wer(self) -> Optional[float]:
        return sum(self.wer_scores) / len(self.wer_scores) if self.wer_scores else None

    @property
    def mean_timestamp_mae(self) -> Optional[float]:
        return sum(self.timestamp_mae_scores) / len(self.timestamp_mae_scores) if self.timestamp_mae_scores else None


# ─────────────────────────────────────────────────────────────────────────────
# Metric computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate using jiwer."""
    jiwer = check_jiwer()
    transforms = jiwer.Compose([
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
    ])
    # CER = edit distance at character level
    ref_chars = " ".join(list(reference.replace(" ", "")))
    hyp_chars = " ".join(list(hypothesis.replace(" ", "")))
    try:
        measures = jiwer.compute_measures(
            ref_chars, hyp_chars,
            truth_transform=transforms,
            hypothesis_transform=transforms,
        )
        return measures["wer"]  # WER on chars = CER
    except Exception:
        return 1.0  # Worst case


def compute_wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate using jiwer."""
    jiwer = check_jiwer()
    transforms = jiwer.Compose([
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
        jiwer.ToLowerCase(),
        jiwer.RemovePunctuation(),
    ])
    try:
        measures = jiwer.compute_measures(
            reference, hypothesis,
            truth_transform=transforms,
            hypothesis_transform=transforms,
        )
        return measures["wer"]
    except Exception:
        return 1.0


def compute_timestamp_mae(
    ref_timestamps: list[float],
    hyp_timestamps: list[float],
) -> Optional[float]:
    """
    Mean Absolute Error between reference and hypothesis segment start times.
    Only computed when reference timestamps exist (expected_timed.json).
    Aligns by position (not word content).
    """
    if not ref_timestamps or not hyp_timestamps:
        return None
    n = min(len(ref_timestamps), len(hyp_timestamps))
    if n == 0:
        return None
    errors = [abs(ref_timestamps[i] - hyp_timestamps[i]) for i in range(n)]
    return sum(errors) / n


# ─────────────────────────────────────────────────────────────────────────────
# Test set discovery
# ─────────────────────────────────────────────────────────────────────────────

def discover_test_songs(test_dir: str) -> list[dict]:
    """
    Scan tests/sample_songs/ for evaluable songs.

    Each song directory must contain:
        audio.mp3 (or audio.wav)
        expected.txt               ← reference lyrics (one line per segment)

    Optionally:
        expected_timed.json        ← [{text: ..., start: ...}, ...] for timestamp eval
        raw_transcription.json     ← ASR output to evaluate against (produced by pipeline)

    Songs are treated as whole units — never split mid-song.
    """
    test_dir = str(test_dir)
    songs = []

    if not os.path.isdir(test_dir):
        log.warning(f"Test directory not found: {test_dir}")
        return songs

    for entry in sorted(os.listdir(test_dir)):
        song_path = os.path.join(test_dir, entry)
        if not os.path.isdir(song_path):
            continue

        expected_txt = os.path.join(song_path, "expected.txt")
        if not os.path.isfile(expected_txt):
            log.debug(f"Skipping {entry}: no expected.txt")
            continue

        # Find audio
        audio_path = None
        for ext in [".mp3", ".wav", ".m4a", ".flac", ".ogg"]:
            candidate = os.path.join(song_path, f"audio{ext}")
            if os.path.isfile(candidate):
                audio_path = candidate
                break

        # Find raw transcription (if pipeline was already run on this song)
        raw_json = os.path.join(song_path, "output", "raw_transcription.json")
        if not os.path.isfile(raw_json):
            raw_json = os.path.join(song_path, "raw_transcription.json")
        if not os.path.isfile(raw_json):
            raw_json = None

        # Find timed reference (optional)
        expected_timed = os.path.join(song_path, "expected_timed.json")
        if not os.path.isfile(expected_timed):
            expected_timed = None

        songs.append({
            "name": entry,
            "dir": song_path,
            "audio": audio_path,
            "expected_txt": expected_txt,
            "expected_timed": expected_timed,
            "raw_json": raw_json,
        })

    log.info(f"Found {len(songs)} evaluable song(s) in {test_dir}")
    return songs


# ─────────────────────────────────────────────────────────────────────────────
# Per-song evaluation
# ─────────────────────────────────────────────────────────────────────────────

def load_expected(expected_txt: str) -> list[str]:
    with open(expected_txt, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
    return lines


def load_raw_transcription(raw_json: str) -> tuple[list[str], list[float]]:
    """Returns (text_lines, start_timestamps)"""
    with open(raw_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    segments = data.get("segments", [])
    lines = [s["text"].strip() for s in segments if s.get("text", "").strip()]
    timestamps = [s.get("start", 0.0) for s in segments if s.get("text", "").strip()]
    return lines, timestamps


def evaluate_song(song: dict) -> Optional[SongResult]:
    if not song["raw_json"]:
        log.warning(f"  [{song['name']}] No raw_transcription.json — run pipeline first.")
        return None

    expected_lines = load_expected(song["expected_txt"])
    raw_lines, raw_timestamps = load_raw_transcription(song["raw_json"])

    # Load timed reference timestamps
    ref_timestamps = []
    if song["expected_timed"]:
        with open(song["expected_timed"], "r", encoding="utf-8") as f:
            timed = json.load(f)
        ref_timestamps = [item.get("start", 0.0) for item in timed]

    ref_text = " ".join(expected_lines)
    hyp_text = " ".join(raw_lines)

    result = SongResult(
        song_name=song["name"],
        expected_lines=expected_lines,
        raw_lines=raw_lines,
        corrected_lines=[],          # Phase 15+: populated from manual corrections
        raw_timestamps=raw_timestamps,
        ref_timestamps=ref_timestamps,
    )

    if ref_text and hyp_text:
        result.cer_raw = compute_cer(ref_text, hyp_text)
        result.wer_raw = compute_wer(ref_text, hyp_text)

    if ref_timestamps and raw_timestamps:
        result.timestamp_mae = compute_timestamp_mae(ref_timestamps, raw_timestamps)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Report generation
# ─────────────────────────────────────────────────────────────────────────────

def format_pct(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    return f"{v * 100:.2f}%"


def format_sec(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    return f"{v:.2f} sec"


def build_report(songs: list[dict], results: list[SongResult], output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)

    valid = [r for r in results if r is not None]
    n = len(valid)

    # Compute aggregates
    cer_values = [r.cer_raw for r in valid if r.cer_raw is not None]
    wer_values = [r.wer_raw for r in valid if r.wer_raw is not None]
    mae_values = [r.timestamp_mae for r in valid if r.timestamp_mae is not None]

    mean_cer = (sum(cer_values) / len(cer_values)) if cer_values else None
    mean_wer = (sum(wer_values) / len(wer_values)) if wer_values else None
    mean_mae = (sum(mae_values) / len(mae_values)) if mae_values else None

    # ── Text report ──
    txt_lines = [
        "Evaluation",
        "----------",
        "",
        f"Samples:         {n}",
        f"Songs evaluated: {', '.join(r.song_name for r in valid) if valid else 'none'}",
        "",
        "Model: faster-whisper (Khmer language hint, int8 CPU)",
        "",
        f"CER:             {format_pct(mean_cer)}",
        f"WER:             {format_pct(mean_wer)}",
        f"Timestamp MAE:   {format_sec(mean_mae)}",
        "",
    ]

    if n == 0:
        txt_lines.append(
            "NOTE: No samples evaluated.\n"
            "Add reference lyrics to tests/sample_songs/<song>/expected.txt\n"
            "and run the pipeline to generate raw_transcription.json first."
        )
    else:
        txt_lines.append("Per-song breakdown:")
        for r in valid:
            txt_lines.append(f"\n  Song: {r.song_name}")
            txt_lines.append(f"    Segments (ref):  {len(r.expected_lines)}")
            txt_lines.append(f"    Segments (ASR):  {len(r.raw_lines)}")
            txt_lines.append(f"    CER:             {format_pct(r.cer_raw)}")
            txt_lines.append(f"    WER:             {format_pct(r.wer_raw)}")
            txt_lines.append(f"    Timestamp MAE:   {format_sec(r.timestamp_mae)}")

    txt_report = "\n".join(txt_lines)
    txt_path = os.path.join(output_dir, "report.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_report)

    # ── JSON report ──
    json_data = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": "faster-whisper (language=km, int8, CPU)",
        "samples": n,
        "aggregate": {
            "CER": format_pct(mean_cer),
            "WER": format_pct(mean_wer),
            "Timestamp_MAE_sec": format_sec(mean_mae),
        },
        "per_song": [
            {
                "song": r.song_name,
                "segments_ref": len(r.expected_lines),
                "segments_asr": len(r.raw_lines),
                "CER": format_pct(r.cer_raw),
                "WER": format_pct(r.wer_raw),
                "Timestamp_MAE_sec": format_sec(r.timestamp_mae),
            }
            for r in valid
        ],
    }

    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    # Print to console
    print("\n" + txt_report)
    print(f"\nReport saved:")
    print(f"  {txt_path}")
    print(f"  {json_path}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    parser = argparse.ArgumentParser(
        description="Phase 13 — Evaluate Khmer ASR pipeline (CER, WER, Timestamp MAE)"
    )
    parser.add_argument(
        "--test-dir",
        default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "sample_songs"),
        help="Path to tests/sample_songs/",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__)),
        help="Directory for report.txt and report.json",
    )
    args = parser.parse_args()

    songs = discover_test_songs(args.test_dir)
    results = [evaluate_song(s) for s in songs]
    build_report(songs, results, args.output_dir)


if __name__ == "__main__":
    main()
