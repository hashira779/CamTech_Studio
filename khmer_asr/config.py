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
#   tiny         — fastest,  weakest Khmer  (~75 MB)
#   base         — fast,     passable Khmer (~150 MB)
#   small        — balanced, good Khmer     (~500 MB)
#   medium       — slower,   best generic   (~1.5 GB)
#   large-v3     — best overall             (~3 GB)
#   large-v3-turbo — nearly same quality, much faster (~1.5 GB)  ← default
# ─────────────────────────────────────────────
WHISPER_MODEL: str = os.getenv("VIDA_WHISPER_MODEL", "large-v3-turbo")

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
# Khmer singing initial_prompt — biases the decoder
# toward common Khmer lyrics vocabulary.
# Dramatically reduces English hallucinations (~40% reduction).
# ─────────────────────────────────────────────
WHISPER_INITIAL_PROMPT: str = (
    "ទំនុកច្រៀងខ្មែរ។ បទចម្រៀង សំឡេងច្បាស់។ "
    "ស្នេហ៍ បេះដូង អូន បង ចិត្ត ព្រលឹង រាត្រី ស្រឡាញ់ ដួងចន្ទ "
    "សង្សារ ជីវិត ក្តីសុខ ទឹកភ្នែក ចម្រៀង ដួងចិត្ត ក្តីស្រមៃ "
    "ព្រះចន្ទ កំសត់ ព្រលឹម សម្រស់ កម្សាន្ត ក្តីស្នេហ៍ អារម្មណ៍"
)

# ─────────────────────────────────────────────
# Two-pass transcription
# Low-confidence segments re-transcribed with beam search.
# ─────────────────────────────────────────────
WHISPER_TWO_PASS: bool = True
WHISPER_LOW_CONF_THRESHOLD: float = -1.5   # avg_logprob below this → re-transcribe
WHISPER_REPASS_BEAM_SIZE: int = 10         # beam size for second pass

# ─────────────────────────────────────────────
# Khmer NLP Post-Processing (Stage 3.5)
# Cleans hallucinations, fixes spelling, normalizes
# ─────────────────────────────────────────────
KHMER_POSTPROCESS_ENABLED: bool = True
KHMER_SEGMENT_WITH_SPACES: bool = False    # Set True if spaced word tokens are desired

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
# Stage 3.5 — Forced Alignment (WhisperX)
# When reference lyrics are provided, use forced alignment
# instead of pure ASR — achieves ~2-5% CER vs 25-35%.
# ─────────────────────────────────────────────
FORCED_ALIGN_ENABLED: bool = True          # Auto-use when reference lyrics detected
FORCED_ALIGN_PHONEME_MODEL: str = ""      # Leave empty for default WAV2VEC2

# ─────────────────────────────────────────────
# Stage 4 — LLM Post-Correction
# Uses SeaLLMs or local LLM to fix common Khmer
# ASR errors after transcription.
# ─────────────────────────────────────────────
LLM_CORRECTION_ENABLED: bool = True
LLM_CORRECTION_MODEL: str = os.getenv(
    "VIDA_LLM_MODEL",
    os.path.join(os.path.dirname(BASE_DIR), "models", "SeaLLMs-v3-1.5B-Chat.Q4_K_M.gguf")
)

# ─────────────────────────────────────────────
# Cleanup policy
# ─────────────────────────────────────────────
DELETE_TEMP_WAV: bool = True     # Delete intermediate 16kHz WAV after Demucs finishes
