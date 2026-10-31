"""
Guards the reload of saved lyrics (backend/lyric_engine.parse_subtitle_file):

  - an .lrc keeps only start times, so a song saved as .lrc + .srt reloads its line ends
    from the .srt, exactly as the user left them
  - the .srt is used only when it holds the same lines at the same starts
Run: python tests/test_saved_line_ends.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.lyric_engine import export_lyrics_to_lrc, export_subtitles_to_srt, parse_subtitle_file

PASS, FAIL = [], []


def check(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg)


lines = [
    {"text": "ផ្កាកុលាបសមានរូបឆោមល្អ", "start": 0.96, "end": 4.16},
    {"text": "ឱ្យខ្ញុំគួរចិត្តចំណង", "start": 12.08, "end": 14.83},
    {"text": "line set by hand", "start": 47.3, "end": 50.6},
    {"text": "next line", "start": 57.38, "end": 60.0},
]

with tempfile.TemporaryDirectory() as d:
    base = os.path.join(d, "song.km")
    export_lyrics_to_lrc(lines, base + ".lrc")
    with open(base + ".srt", "w", encoding="utf-8") as f:
        f.write(export_subtitles_to_srt(lines))

    print("=== saved as .lrc and .srt ===")
    got = parse_subtitle_file(base + ".lrc")
    check([round(l["end"], 2) for l in got] == [4.16, 14.83, 50.6, 60.0], "line ends come back exactly as saved")
    check([round(l["start"], 2) for l in got] == [0.96, 12.08, 47.3, 57.38], "and the starts too")

    print("\n=== an .srt with other lines is not used ===")
    with open(base + ".srt", "w", encoding="utf-8") as f:
        f.write(export_subtitles_to_srt(lines[:2] + [{"text": "a human caption", "start": 47.3, "end": 49.0}] + lines[3:]))
    got = parse_subtitle_file(base + ".lrc")
    check(got[2]["text"] == "line set by hand", "the .lrc's own lines are kept when the .srt differs")

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
