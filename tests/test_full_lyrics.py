"""
Guards the full copy of the last sync saved next to each song (backend/services/lyric_alignment.py):

  - the word timings, confidence and hand-set marks come back exactly as saved
  - a subtitle file changed after it (edited in another program) is newer work and wins
  - a broken or empty copy is ignored instead of loading nothing
Run: python tests/test_full_lyrics.py
"""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.lyric_alignment import load_full_lyrics, save_full_lyrics

PASS, FAIL = [], []


def check(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg)


with tempfile.TemporaryDirectory() as d:
    audio = os.path.join(d, "song.mp3")
    open(audio, "wb").close()
    lines = [
        {"text": "កូនអ្ហើយជឿតែម៉ែទៅ", "start": 8.72, "end": 11.9, "confidence": 0.41,
         "words": [{"word": "កូន", "start": 8.72, "end": 9.1}, {"word": "អ្ហើយ", "start": 9.1, "end": 9.8}]},
        {"text": "ម៉ែត្រូវឲ្យកូនមានប្តីហើយ", "start": 12.1, "end": 16.0, "confidence": 1, "timing_source": "manual",
         "words": [{"word": "ម៉ែ", "start": 12.1, "end": 12.5}]},
    ]
    save_full_lyrics(lines, audio)
    got = load_full_lyrics(audio)
    check(got is not None and got[0] == lines, "the last sync comes back exactly: times, words, confidence, hand-set marks")

    srt = os.path.join(d, "song.srt")
    open(srt, "w").close()
    later = time.time() + 60
    os.utime(srt, (later, later))
    check(load_full_lyrics(audio, os.path.getmtime(srt)) is None, "a subtitle file edited afterwards wins")
    check(load_full_lyrics(audio, os.path.getmtime(audio)) is not None, "an older subtitle file does not")

    with open(os.path.join(d, "song.vida.json"), "w", encoding="utf-8") as f:
        f.write("{broken")
    check(load_full_lyrics(audio) is None, "a broken copy is ignored")
    with open(os.path.join(d, "song.vida.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "lines": []}, f)
    check(load_full_lyrics(audio) is None, "an empty copy is ignored")

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
