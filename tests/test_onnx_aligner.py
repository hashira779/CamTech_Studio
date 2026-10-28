"""
Guards backend/onnx_aligner.py, the torch-free word aligner:

  - the numpy forced alignment finds the same path and scores as torchaudio's
  - letter spans (start, end, mean probability) match torchaudio's merge_tokens
  - repeated letters get a blank between them, and too-long lyrics are refused
Run: python tests/test_onnx_aligner.py   (the torchaudio comparison is skipped without torch)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.onnx_aligner import forced_align, merge_tokens

PASS, FAIL = [], []


def check(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg)


def log_probs(rng, T, C):
    x = rng.normal(size=(T, C)).astype(np.float32) * 3
    return x - np.log(np.exp(x).sum(axis=1, keepdims=True))


print("=== the path is a valid CTC path ===")
rng = np.random.default_rng(0)
em = log_probs(rng, 60, 6)
targets = [1, 2, 2, 3, 5]
tokens, scores = forced_align(em, targets)
spans = merge_tokens(tokens, np.exp(scores))
check([s.token for s in spans] == targets, "every letter appears once, in order, and the doubled 2 stays two letters")
check(all(tokens[s.end - 1] != 0 for s in spans) and all(np.all(tokens[s.start:s.end] == s.token) for s in spans),
      "spans cover exactly the frames of their letter")
check(np.allclose(scores, em[np.arange(60), tokens]), "each frame's score is its letter's log-probability")
try:
    forced_align(log_probs(rng, 3, 6), [1, 2, 3, 4])
    check(False, "lyrics longer than the audio are refused")
except ValueError:
    check(True, "lyrics longer than the audio are refused")

print("\n=== same answer as torchaudio ===")
try:
    import torch
    import torchaudio.functional as AF
except ImportError:
    torch = None
    print("  (torch not installed: skipped)")
if torch is not None:
    same_path = same_spans = 0
    cases = 200
    for k in range(cases):
        T, C = int(rng.integers(20, 300)), int(rng.integers(4, 30))
        n = int(rng.integers(1, max(2, T // 3)))
        tg = [int(x) for x in rng.integers(1, C, size=n)]
        em = log_probs(rng, T, C)
        a_t, s_t = AF.forced_align(torch.from_numpy(em)[None], torch.tensor([tg], dtype=torch.int32), blank=0)
        a_n, s_n = forced_align(em, tg)
        if np.array_equal(a_t[0].numpy(), a_n) and np.allclose(s_t[0].numpy(), s_n, atol=1e-5):
            same_path += 1
        sp_t = AF.merge_tokens(a_t[0], s_t[0].exp(), blank=0)
        sp_n = merge_tokens(a_n, np.exp(s_n))
        if len(sp_t) == len(sp_n) and all(x.token == y.token and x.start == y.start and x.end == y.end
                                          and abs(x.score - y.score) < 1e-5 for x, y in zip(sp_t, sp_n)):
            same_spans += 1
    check(same_path == cases, f"same path and scores on {same_path}/{cases} random songs")
    check(same_spans == cases, f"same letter spans on {same_spans}/{cases} random songs")

print(f"\n{'ALL PASS' if not FAIL else f'{len(FAIL)} FAILED'} - {len(PASS)}/{len(PASS) + len(FAIL)} checks passed")
sys.exit(1 if FAIL else 0)
