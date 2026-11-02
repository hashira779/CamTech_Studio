"""
The word aligner's model on onnxruntime, without torch.

Same model as torchaudio's MMS_FA, converted once by tools/export_aligner_onnx.py. Measured on a
5.4 min song: the same letter probabilities as torch (largest difference 0.005), a little faster
on the CPU, and the worker no longer loads torch, so aligning needs much less free memory.
(An 8-bit copy was tried: it changed 6% of the frames and was slower, so it is not used.)
ctc_align uses this whenever the converted model is there and falls back to torch otherwise.

Also holds the CTC forced alignment itself (Viterbi over the lyric's letters), in numpy, so the
same code aligns whichever model produced the letter probabilities.
"""
import json
import os
import threading
from collections import namedtuple
from typing import Dict, List, Optional, Sequence

import numpy as np

_MODELS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
MODEL_PATH = os.path.join(_MODELS, "mms_fa.onnx")
VOCAB_PATH = os.path.join(_MODELS, "mms_fa_vocab.json")

_LOCK = threading.Lock()
_SESSION = None
_VOCAB: Optional[Dict[str, int]] = None

TokenSpan = namedtuple("TokenSpan", "token start end score")


def is_available() -> bool:
    """True when the converted model is there and onnxruntime is installed (found, not imported)."""
    if os.environ.get("VIDA_ALIGNER") == "torch":
        return False
    if not (os.path.exists(MODEL_PATH) and os.path.exists(VOCAB_PATH)):
        return False
    import importlib.util
    try:
        return importlib.util.find_spec("onnxruntime") is not None
    except (ImportError, ValueError):
        return False


def get_vocab() -> Dict[str, int]:
    global _VOCAB
    if _VOCAB is None:
        with open(VOCAB_PATH, encoding="utf-8") as f:
            _VOCAB = json.load(f)
    return _VOCAB


def _session():
    global _SESSION
    with _LOCK:
        if _SESSION is None:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            opts.intra_op_num_threads = min(8, os.cpu_count() or 4)
            # Without the memory pool the model peaks 0.6 GB lower (2.7 -> 2.1 GB, measured).
            opts.enable_cpu_mem_arena = False
            _SESSION = ort.InferenceSession(MODEL_PATH, opts, providers=["CPUExecutionProvider"])
    return _SESSION


def emission(data: np.ndarray, sample_rate: int, hop: int, chunk_s: float, context_s: float) -> np.ndarray:
    """
    Per-frame log-probabilities (T, C) for mono float32 audio, in chunks with context on both
    sides, exactly as ctc_align.compute_emission does with torch.
    """
    sess = _session()
    n = len(data)
    chunk = int(chunk_s * sample_rate) // hop * hop
    ctx = int(context_s * sample_rate) // hop * hop
    pieces = []
    for s in range(0, n, chunk):
        core = min(chunk, n - s) // hop
        if core <= 0:
            break
        a, b = max(0, s - ctx), min(n, s + chunk + ctx)
        seg = data[a:b].astype(np.float32, copy=False)
        if len(seg) < 2 * hop:
            seg = np.pad(seg, (0, 2 * hop - len(seg)))
        # The torch wrapper's input layer-norm, over the whole segment.
        seg = (seg - seg.mean()) / np.sqrt(seg.var() + 1e-5)
        logits = sess.run(None, {"audio": seg[None, :].astype(np.float32)})[0][0]
        logits = logits - logits.max(axis=-1, keepdims=True)
        logp = logits - np.log(np.exp(logits).sum(axis=-1, keepdims=True))
        off = (s - a) // hop
        em = logp[off:off + core]
        if len(em) < core:
            em = np.concatenate([em, np.repeat(em[-1:], core - len(em), axis=0)])
        pieces.append(em)
    return np.concatenate(pieces).astype(np.float32) if pieces else np.zeros((0, len(get_vocab())), np.float32)


def forced_align(em: np.ndarray, targets: Sequence[int], blank: int = 0):
    """
    CTC forced alignment: the most likely path through `targets` (no blanks in it) over the
    frames of `em` (T, C log-probabilities). Returns (token per frame, log-prob per frame),
    like torchaudio.functional.forced_align. Ties keep the current letter, as torchaudio does.
    """
    T = em.shape[0]
    ext = np.full(2 * len(targets) + 1, blank, dtype=np.int64)
    ext[1::2] = targets
    S = len(ext)
    if S > 2 * T + 1:
        raise ValueError("targets are longer than the audio")
    skip = np.zeros(S, dtype=bool)  # a letter may follow the letter before it directly (no blank)
    skip[3::2] = ext[3::2] != ext[1:-2:2]

    neg = np.float32(-np.inf)
    alpha = np.full(S, neg, dtype=np.float32)
    alpha[0] = em[0, ext[0]]
    alpha[1] = em[0, ext[1]]
    back = np.zeros((T, S), dtype=np.int8)
    cand = np.empty((3, S), dtype=np.float32)
    for t in range(1, T):
        cand[0] = alpha
        cand[1, 0] = neg
        cand[1, 1:] = alpha[:-1]
        cand[2, :2] = neg
        cand[2, 2:] = np.where(skip[2:], alpha[:-2], neg)
        choice = cand.argmax(axis=0)
        back[t] = choice
        alpha = cand[choice, np.arange(S)] + em[t, ext]

    s = S - 1 if alpha[S - 1] >= alpha[S - 2] else S - 2
    if not np.isfinite(alpha[s]):
        raise ValueError("no alignment path")
    states = np.empty(T, dtype=np.int64)
    for t in range(T - 1, -1, -1):
        states[t] = s
        s -= int(back[t, s])
    tokens = ext[states]
    return tokens, em[np.arange(T), tokens]


def merge_tokens(tokens: np.ndarray, probs: np.ndarray, blank: int = 0) -> List[TokenSpan]:
    """Frames of the same letter in a row -> one span (start, end frames; mean probability)."""
    change = np.flatnonzero(np.diff(tokens, prepend=-1, append=-1) != 0)
    return [
        TokenSpan(int(tokens[a]), int(a), int(b), float(probs[a:b].mean()))
        for a, b in zip(change[:-1], change[1:])
        if tokens[a] != blank
    ]
