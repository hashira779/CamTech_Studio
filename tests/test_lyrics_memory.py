"""
Guards the lyrics memory (backend/khmer_lyric_matcher.py):

  - lyrics the user pasted for Paste & Align are remembered as theirs (verified)
  - they replace an AI transcription saved before, and an AI transcription never replaces them
  - a song is found by its title, with its verified flag
Run: python tests/test_lyrics_memory.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.khmer_lyric_matcher as km

PASS, FAIL = [], []


def check(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg)


with tempfile.TemporaryDirectory() as d:
    km.DB_PATH = os.path.join(d, "lyrics.json")
    ai = ["ថ្នមអើយ ថ្នមស្នេ", "ថ្នមបំពេ មាសមេ", "បងអង្អែល", "ស្នេហ៍ចិត្តមួយ"]
    yours = ["ថ្នមអើយ ថ្នមស្នេហ៍", "ថ្នមបំពេ មាសមេតែមួយ", "បងអង្អែលអង្អែល មិនឲ្យកែវព្រួយ", "ស្នេហ៍ចិត្តមួយ ថ្លើមមួយណាតែវ"]

    km.save_to_local_lyrics_db("ថ្នមចិត្ត", "ស៊ីន ស៊ីសាមុត", ai)
    check(km.lookup_lyrics("ថ្នមចិត្ត") == (ai, False), "an AI transcription is remembered as a draft")

    km.save_to_local_lyrics_db("ថ្នមចិត្ត", "ស៊ីន ស៊ីសាមុត", yours, verified=True)
    check(km.lookup_lyrics("ថ្នមចិត្ត") == (yours, True), "the user's pasted lyrics replace it, marked as theirs")

    km.save_to_local_lyrics_db("ថ្នមចិត្ត", "ស៊ីន ស៊ីសាមុត", ai)
    check(km.lookup_lyrics("ថ្នមចិត្ត") == (yours, True), "a later AI transcription never replaces the user's lyrics")

    km.save_to_local_lyrics_db("ថ្នមចិត្ត", "ស៊ីន ស៊ីសាមុត", yours[:3] + ["edited line"], verified=True)
    check(km.lookup_lyrics("ថ្នមចិត្ត")[0][-1] == "edited line", "the user's newest paste replaces their older one")
    check(km.search_local_lyrics_db("ថ្នមចិត្ត")[0] == yours[0], "the older lookup still answers with the lines")
    check(km.lookup_lyrics("បទផ្សេង") is None, "an unknown song has nothing remembered")

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
