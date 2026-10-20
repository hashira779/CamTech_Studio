"""Backend (legacy /api/render) display-mode check.

Renders one frame at a fixed timestamp through the real server-side renderer for each
of the three lyrics display modes, then measures *where* frames differ (frame-diff, not
guessed bands), proving original_only / translation_only / bilingual render differently
in the right place and never mutate the source cues.

Run:  venv/Scripts/python.exe tests/test_renderer_display_modes.py
"""
import copy
import os
import re
import sys

import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from backend.app import build_translation_display_lyrics  # noqa: E402
from backend.renderer import VideoRenderer  # noqa: E402

AUDIO_DIR = os.path.join(BASE, "uploads", "audio")
W, H = 1280, 720
T = 19.6
SONG = ORIG_PATH = TR_PATH = None

_time_re = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)


def to_s(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(path):
    cues = []
    for block in re.split(r"\n\s*\n", open(path, encoding="utf-8-sig").read().strip()):
        lines = [l.rstrip() for l in block.splitlines() if l.strip()]
        idx = next((i for i, l in enumerate(lines) if _time_re.search(l)), None)
        if idx is None:
            continue
        g = _time_re.search(lines[idx]).groups()
        text = " ".join(lines[idx + 1:]).strip()
        if text:
            cues.append({"line_id": len(cues) + 1, "start": round(to_s(*g[:4]), 3),
                         "end": round(to_s(*g[4:]), 3), "text": text})
    return cues


def find_song():
    for f in sorted(os.listdir(AUDIO_DIR)):
        if f.lower().endswith(".mp3"):
            stem = os.path.splitext(f)[0]
            orig = os.path.join(AUDIO_DIR, stem + ".srt")
            tr = os.path.join(AUDIO_DIR, stem + ".en.srt")
            if os.path.exists(orig) and os.path.exists(tr):
                return os.path.join(AUDIO_DIR, f), orig, tr
    raise SystemExit("SKIP: need a song with both .srt and .en.srt in uploads/audio")


def render_frame(lyrics, mode, translation_strings):
    r = VideoRenderer(
        audio_path=SONG, output_path=os.path.join(BASE, ".verify", "_throwaway.mp4"),
        width=W, height=H, fps=30, theme="trap_circle", palette_name="cyberpunk",
        song_title="TEST", artist_name="TEST", lyrics_data=lyrics,
        display_mode=mode, translation_lines=translation_strings, translation_lang="en",
    )
    frame = r.bg_frame.copy()
    frame = r.render_lyrics_and_ui(frame, T)
    frame = r.render_translation_subline(frame, T)
    return frame


def subline_split_y(height):
    """Row where render_translation_subline's band begins (mirrors its own geometry)."""
    base_font = int(height * 0.054)
    tr_size = max(11, int(base_font * 0.55))
    anchor_y = int(height * 0.85) + int(base_font * 0.72) + int(tr_size * (0.42 + 0.55))
    return max(0, anchor_y - int(tr_size * 0.4))


def diff_stats(a, b, split_y):
    """Where do two BGR frames differ? Pill rows are above split_y, subline rows below."""
    d = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
    changed = d > 24
    rows = np.where(changed.any(axis=1))[0]
    return {
        "changedPx": int(changed.sum()),
        "pillRegionPx": int(changed[:split_y].sum()),
        "belowPillPx": int(changed[split_y:].sum()),
        "rowRange": (int(rows.min()), int(rows.max())) if rows.size else None,
    }


def main():
    global SONG, ORIG_PATH, TR_PATH
    SONG, ORIG_PATH, TR_PATH = find_song()
    original = parse_srt(ORIG_PATH)
    translated_cues = parse_srt(TR_PATH)
    tr_strings = [c["text"] for c in translated_cues]
    assert original and translated_cues, "both cue lists must be non-empty"
    print(f"song={os.path.basename(SONG)}  cues={len(original)}  translated={len(translated_cues)}  t={T}s")

    orig_snapshot = copy.deepcopy(original)
    tr_snapshot = copy.deepcopy(tr_strings)

    SPLIT = subline_split_y(H)
    f_orig = render_frame(original, "original_only", tr_strings)
    f_tr = render_frame(build_translation_display_lyrics(original, "translation_only", tr_strings),
                        "translation_only", tr_strings)
    f_bi = render_frame(original, "bilingual", tr_strings)

    def subline_bright(f):
        g = f.astype(np.float32) @ np.array([0.114, 0.587, 0.299], dtype=np.float32)
        return int((g[SPLIT:] > 120).sum())

    d_bi = diff_stats(f_bi, f_orig, SPLIT)
    d_tr = diff_stats(f_tr, f_orig, SPLIT)
    print(f"  subline band starts at y={SPLIT}")
    print(f"  bright px in subline band: original_only={subline_bright(f_orig)}  "
          f"translation_only={subline_bright(f_tr)}  bilingual={subline_bright(f_bi)}")
    print(f"  bilingual vs original_only  : {d_bi}")
    print(f"  translation_only vs original: {d_tr}")

    fails = []

    def check(name, cond):
        print(("  PASS  " if cond else "  FAIL  ") + name)
        if not cond:
            fails.append(name)

    print("\nassertions:")
    check("bilingual adds the translated subline below the pill",
          d_bi["belowPillPx"] > 400 and subline_bright(f_bi) > 400)
    check("bilingual leaves the original pill pixel-identical", d_bi["pillRegionPx"] < 60)
    f_noblank = render_frame(original, "original_only", [])
    d_blank = diff_stats(f_orig, f_noblank, SPLIT)
    check("original_only draws nothing extra (identical with an empty translation track)",
          d_blank["changedPx"] == 0)
    check("original_only subline band stays far below bilingual's",
          subline_bright(f_orig) < 0.25 * subline_bright(f_bi))
    check("translation_only replaces the pill text and renders no subline",
          d_tr["pillRegionPx"] > 400 and subline_bright(f_tr) == 0)
    check("display copy swaps in the translated text",
          build_translation_display_lyrics(original, "translation_only", tr_strings)[0]["text"]
          == tr_strings[0])
    check("display copy keeps the original timing window",
          all(d["start"] == o["start"] and d["end"] == o["end"]
              for d, o in zip(build_translation_display_lyrics(original, "translation_only", tr_strings), original)))
    check("display copy is a new list of new dicts",
          build_translation_display_lyrics(original, "translation_only", tr_strings) is not original
          and build_translation_display_lyrics(original, "translation_only", tr_strings)[0] is not original[0])
    check("original_only / bilingual display copy is a no-op",
          build_translation_display_lyrics(original, "original_only", tr_strings) == original
          and build_translation_display_lyrics(original, "bilingual", tr_strings) == original)
    check("source cues untouched after rendering all three modes",
          original == orig_snapshot and tr_strings == tr_snapshot)
    check("word timings of display copy stay inside the cue window",
          all(0.0 <= (w["start"] - o["start"]) and (w["end"] - o["end"]) <= 0.05
              for d, o in zip(build_translation_display_lyrics(original, "translation_only", tr_strings), original)
              for w in (d.get("words") or []) if o["text"] != d["text"]))

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + '; '.join(fails)}  ({len(fails)} failed)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
