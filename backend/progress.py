"""
Progress of the running lyrics job (transcribe or align), polled by the studio through
GET /api/transcribe/progress. One job at a time: the heavy models share one budget anyway.
"""

from typing import Any, Dict

_progress: Dict[str, Any] = {"status": "idle", "percent": 0, "stage": ""}


def update_transcribe_progress(percent: int, stage: str) -> None:
    global _progress
    _progress = {
        "status": "in_progress" if percent < 100 else "complete",
        "percent": percent,
        "stage": stage,
    }


def transcribe_progress() -> Dict[str, Any]:
    return dict(_progress)
