"""
Central configuration for the Khmer Singing Lyrics Pipeline.
All tuneable parameters live here — override via environment variables or CLI flags.
"""

import os

# ─────────────────────────────────────────────
# Device  (cpu | cuda | auto)
# Ryzen 4000 has no CUDA — use cpu.
# Set VIDA_DEVICE=auto if you add a GPU later.
# ─────────────────────────────────────────────
DEVICE: str = os.getenv("VIDA_DEVICE", "cpu")

# ─────────────────────────────────────────────
# faster-whisper model size
#   tiny   — fastest,  weakest Khmer  (~75 MB)
#   base   — fast,     passable Khmer (~150 MB)
#   small  — balanced, good Khmer     (~500 MB)  ← default
#   medium — slower,   best Khmer     (~1.5 GB)
#   large-v3 — best overall           (~3 GB)
# ─────────────────────────────────────────────
WHISPER_MODEL: str = os.getenv("VIDA_WHISPER_MODEL", "medium")

# If you have a community fine-tuned Khmer Whisper checkpoint on HuggingFace,
# set this to its path or HF repo-id.  Leave "" to use the standard OpenAI model.
WHISPER_KHMER_MODEL: str = os.getenv("VIDA_WHISPER_KHMER_MODEL", "")

# ─────────────────────────────────────────────
# faster-whisper inference options
# ─────────────────────────────────────────────
WHISPER_COMPUTE_TYPE: str = "int8"        # int8 is fastest on CPU with acceptable quality
WHISPER_LANGUAGE: str = "km"             # Khmer ISO-639-1 code
WHISPER_BEAM_SIZE: int = 3               # Lower = faster on CPU (default openai=5)
WHISPER_BEST_OF: int = 1
WHISPER_TEMPERATURE: float = 0.0        # Greedy decoding — no hallucination drift
WHISPER_WORD_TIMESTAMPS: bool = True    # Needed for LRC/SRT generation
WHISPER_VAD_FILTER: bool = True         # Skip silence automatically
WHISPER_VAD_THRESHOLD: float = 0.3     # Lower than default (0.5) — catches singing
WHISPER_CONDITION_ON_PREV: bool = False # Prevents repeating hallucinations in long songs
WHISPER_NO_SPEECH_THRESHOLD: float = 0.4  # Lower than default 0.6 — singing has low ASR confidence
WHISPER_LOGPROB_THRESHOLD: float = -2.0   # More permissive than default -1.0
WHISPER_CPU_THREADS: int = int(os.getenv("VIDA_CPU_THREADS", "8"))  # Ryzen 4000 has 8 threads

# ─────────────────────────────────────────────
# Demucs vocal separator
# ─────────────────────────────────────────────
DEMUCS_MODEL: str = os.getenv("VIDA_DEMUCS_MODEL", "htdemucs")  # htdemucs = fastest+best
DEMUCS_SHIFTS: int = 1          # 1 = fastest (no random shifts); higher = slightly better
DEMUCS_OVERLAP: float = 0.25    # segment overlap — 0.25 is default
DEMUCS_SEGMENT: float = 7.8    # seconds per chunk — reduce if OOM on low RAM
DEMUCS_JOBS: int = 1            # parallel jobs — keep 1 on CPU to avoid OOM

# ─────────────────────────────────────────────
# Audio preprocessing
# ─────────────────────────────────────────────
AUDIO_SAMPLE_RATE: int = 16000   # Whisper requires 16kHz
AUDIO_CHANNELS: int = 1          # Mono

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
EVAL_DIR = os.path.join(BASE_DIR, "evaluation")
TESTS_DIR = os.path.join(BASE_DIR, "tests")
SAMPLE_SONGS_DIR = os.path.join(TESTS_DIR, "sample_songs")

# ─────────────────────────────────────────────
# Cleanup policy
# ─────────────────────────────────────────────
DELETE_TEMP_WAV: bool = True     # Delete intermediate 16kHz WAV after Demucs finishes
