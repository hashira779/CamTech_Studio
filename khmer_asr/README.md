# Khmer ASR Singing Lyrics Pipeline — README
<!-- Phase 1: First working implementation -->

## What This Is

A **local, CPU-compatible pipeline** that extracts timestamped Khmer lyrics
from any song audio file. No cloud, no database, no GPU required.

```
song.mp3
  │
  ▼ Stage 1 — FFmpeg (bundled)
16kHz mono WAV
  │
  ▼ Stage 2 — Demucs htdemucs (CPU)
vocals.wav
  │
  ▼ Stage 3 — faster-whisper (Khmer, int8, CPU)
raw_transcription.json  ←── always preserved, never modified
  │
  ├── lyrics.txt
  ├── lyrics.lrc   ←── load directly into VIDA
  └── lyrics.srt
```

## Requirements

- Windows 10/11 (tested on Ryzen 4000)
- Python 3.9+
- ~2 GB disk space (models download on first use)
- **No CUDA / GPU required**

## Quick Install

```bat
cd D:\Project\VIDA\khmer_asr
install.bat
```

This installs CPU-only PyTorch first, then Demucs, then everything else.

## Usage

### Transcribe a song (full pipeline)
```bat
venv\Scripts\python khmer_asr\pipeline.py --input uploads\my_khmer_song.mp3
```

### Skip vocal separation (faster, use if already vocals-only)
```bat
venv\Scripts\python khmer_asr\pipeline.py --input uploads\vocals.wav --skip-separation
```

### Use a larger model for better accuracy
```bat
venv\Scripts\python khmer_asr\pipeline.py --input song.mp3 --model medium
```

### Use a custom fine-tuned Khmer Whisper checkpoint
```bat
venv\Scripts\python khmer_asr\pipeline.py --input song.mp3 --khmer-model username/khmer-whisper-singing
```

### Regenerate LRC/SRT without re-running Whisper
```bat
venv\Scripts\python khmer_asr\pipeline.py --regen output\my_song\raw_transcription.json
```

## Output Files

Each song gets its own folder under `output/<song_name>/`:

| File | Description |
|------|-------------|
| `raw_transcription.json` | **Never delete this.** Complete ASR output with timestamps |
| `lyrics.txt` | Plain text, one line per segment |
| `lyrics.lrc` | Standard LRC karaoke format (load in VIDA) |
| `lyrics.srt` | SRT subtitle format |
| `vocals.wav` | Isolated vocals (Demucs output) |
| `accompaniment.wav` | Background music (Demucs output) |

## Model Speed Guide (Ryzen 4000, CPU)

| Model | Size | Khmer Quality | Time / 4-min song |
|-------|------|--------------|-------------------|
| `tiny` | 75 MB | ★★☆☆☆ | ~1 min |
| `base` | 150 MB | ★★★☆☆ | ~2 min |
| `small` | 500 MB | ★★★★☆ | ~5 min |
| `medium` | 1.5 GB | ★★★★★ | ~15 min |
| `large-v3` | 3 GB | ★★★★★ | ~40 min |

**Recommended:** `small` for development, `medium` for final production export.

## Configuration (`config.py`)

All settings can be overridden via environment variables:

```bat
set VIDA_WHISPER_MODEL=medium
set VIDA_DEVICE=cpu
set VIDA_CPU_THREADS=8
python khmer_asr\pipeline.py --input song.mp3
```

## Phase 13 — Evaluation

To calculate real CER/WER after adding reference lyrics:

1. Add your test song:
   ```
   tests\sample_songs\my_song\
       audio.mp3
       expected.txt   ← one line per lyric segment
   ```
2. Run evaluation:
   ```bat
   python khmer_asr\evaluation\evaluate.py
   ```
3. See results in `evaluation\report.txt` and `report.json`.

**Note:** The evaluator never invents numbers. It prints `N/A` unless
`expected.txt` exists and `raw_transcription.json` has been generated.

## Phase 15 — Quality Testing

```bat
python khmer_asr\tests\test_pipeline.py --model small --skip-separation
```

Prints a side-by-side comparison of expected vs. ASR output for every test song.

## Future Roadmap (Phases 14–16)

```
Phase 14 ✅  CPU optimization   — sequential loading, int8, VAD, temp cleanup
Phase 15 ✅  Quality testing    — tests/sample_songs/ + evaluation/report.json
Phase 16 ⏳  Model improvement  — fine-tuned Khmer singing Whisper

Future pipeline:
    Khmer Song
        ↓  Demucs htdemucs
    Vocal Separation
        ↓  Pyannote / custom
    Singing Detection
        ↓  Fine-tuned Whisper (km, singing corpus)
    Khmer Singing Whisper
        ↓  n-gram LM / khmernltk
    Khmer Language Model
        ↓  DTW / CTC alignment
    Timestamp Alignment
        ↓
    Final Khmer Lyrics
```

## Design Principles

1. No database — local files only
2. CPU compatible — Ryzen 4000 tested
3. Existing pretrained models first
4. `raw_transcription.json` is sacred — never overwritten
5. Never hallucinate lyrics (`temperature=0`, `condition_on_prev=False`)
6. Human corrections become training data (Phase 16)
7. Evaluate on separate test set — no data leakage
8. Every model is replaceable via `config.py`
9. Do not claim accuracy without real measurements
