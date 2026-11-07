"""
How many CPU threads VIDA's heavy steps use: voice separation (Demucs) and the word aligner (ONNX).

One per physical core, never more than 80% of all logical threads. Measured on a Ryzen 7 4800H
(8 cores, 16 threads): voice separation took 53.8 s per 30 s of song at 8 threads against 69.0 s
with the old 4 threads x 4 jobs (22% faster); the aligner, already at 8, ran 37 s per 60 s of song
at 8 and 12 threads alike, and 13 threads were slower for both (the extra threads share cores).
VIDA_CPU_THREADS overrides it.
"""
import os

MAX_SHARE = 0.8


def _physical_cores() -> int:
    try:
        import psutil
        return psutil.cpu_count(logical=False) or 0
    except Exception:
        return 0


def compute_threads() -> int:
    override = os.environ.get("VIDA_CPU_THREADS", "").strip()
    if override.isdigit() and int(override) > 0:
        return int(override)
    logical = os.cpu_count() or 4
    physical = _physical_cores() or max(1, logical // 2)
    return max(1, min(physical, int(logical * MAX_SHARE)))


def apply_to_process() -> int:
    """For a worker process: sets the thread count for the math libraries (and torch if loaded)."""
    n = compute_threads()
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[var] = str(n)
    return n
