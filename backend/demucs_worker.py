"""Isolated runner for Demucs; see vocal_separator.separate_vocals_demucs for why."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.vocal_separator import _PROGRESS_PREFIX, _separate_inproc


def main() -> int:
    audio_path, out_path, vocals_out, accompaniment_out = sys.argv[1:5]
    model_name, device = sys.argv[5], sys.argv[6]

    def forward_progress(percent: int, message: str) -> None:
        print(f"{_PROGRESS_PREFIX}{percent}|{message}", flush=True)

    result = _separate_inproc(audio_path, vocals_out, accompaniment_out, device, model_name, forward_progress)
    Path(out_path).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
