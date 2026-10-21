"""
The single budget for throwaway model processes (Demucs, the CTC word aligner).

Each of them loads torch, and this machine runs out of commit address space when two do it at the
same time — torch then faults natively (0xc0000005) instead of raising MemoryError, so the failure
cannot be caught or reported properly from Python. Holding this lock across a child run makes the
studio queue its heavy work instead of crashing through it.
"""

import threading

LOCK = threading.Lock()
ACQUIRE_TIMEOUT_S = 1800.0


def run_locked(work, timeout=ACQUIRE_TIMEOUT_S):
    """Run `work()` with exclusive access to the model budget, or raise TimeoutError."""
    if not LOCK.acquire(timeout=timeout):
        raise TimeoutError(f"the model budget is still held after {timeout:.0f}s")
    try:
        return work()
    finally:
        LOCK.release()
