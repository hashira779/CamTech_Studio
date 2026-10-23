"""Isolated runner for the CTC word aligner; see ctc_align.ctc_align_lyrics for why."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.ctc_align import MIN_CONFIDENCE, _ctc_align_lyrics_inproc


import time


def main() -> int:
    t0 = time.time()
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    n_lines = len(job.get("lyrics_lines", []))
    print(f"[CTC Worker] 🎙️ Processing forced alignment for {n_lines} lines...", flush=True)
    segments = [tuple(s) for s in job["vocal_segments"]] if job.get("vocal_segments") else None
    lines = _ctc_align_lyrics_inproc(
        job["lyrics_lines"],
        job["audio_path"],
        vocal_segments=segments,
        min_confidence=job.get("min_confidence", MIN_CONFIDENCE),
    )
    elapsed = time.time() - t0
    if lines:
        print(f"[CTC Worker] ✅ Word alignment finished in {elapsed:.2f}s ({len(lines)} lines aligned)", flush=True)
    else:
        print(f"[CTC Worker] ⚠️ Word alignment returned no match in {elapsed:.2f}s (reverting to acoustic cadence)", flush=True)
    Path(sys.argv[2]).write_text(json.dumps({"lines": lines}, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
