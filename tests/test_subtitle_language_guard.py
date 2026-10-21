"""
Regression guard for "why did the original lyrics turn into English?":

  - language detection must be decided by the DOMINANT script, not one stray character
  - a translated companion track ("-tr") is never eligible as the original
  - a caption whose content language differs from the trusted song language is rejected
    (an English translation must not replace Vietnamese/Khmer originals)
Run: python tests/test_subtitle_language_guard.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.lyric_engine import detect_text_language_ex, find_matching_subtitles

PASS, FAIL = [], []

VI_SONG = "THIÊN ĐƯỜNG VỚI NGƯỜI THƯƠNG - Phương Mỹ Chi x DTAP"
VI_VTT = """WEBVTT
Kind: captions
Language: en

00:00:10.762 --> 00:00:13.140
Hỡi ơi người ơi

00:00:13.140 --> 00:00:15.432
Em không cần tìm kiếm đâu xa

00:00:15.432 --> 00:00:20.349
Vì em biết là anh thương em nhất mà

00:00:20.349 --> 00:00:22.441
Hỡi ơi người ơi

00:00:22.441 --> 00:00:24.739
Ta đâu cần đi đâu nữa đâu

00:00:24.739 --> 00:00:29.622
Cõi thiên đường là ngồi đáy giếng với người mình thương

00:00:57.292 --> 00:00:59.823
Đôi ta ở đây, đâu cần hay

00:01:02.331 --> 00:01:06.683
Nơi giếng sâu ta ngồi cạnh nhau

00:02:02.740 --> 00:02:05.000
បងមានស្រឡាញ់អូនទេ? (Bong sro-lanh uon tê?)
"""

EN_SRT = """1
00:00:10,760 --> 00:00:13,140
Oh my dear, oh my dear

2
00:00:13,140 --> 00:00:15,430
I don't need to search anywhere far

3
00:00:15,430 --> 00:00:20,350
Because I know you love me the most by far

4
00:00:20,350 --> 00:00:22,440
Oh my dear, oh my dear

5
00:00:22,440 --> 00:00:24,740
We don't need to go anywhere else at all

6
00:00:24,740 --> 00:00:29,620
Paradise is sitting at the bottom of a well with the one I adore

7
00:00:29,620 --> 00:00:32,120
This love is as sweet as freshly squeezed orange juice

8
00:00:32,120 --> 00:00:34,370
There's no way it can escape anyone's view

9
00:02:02,740 --> 00:02:05,000
Do you love me? (Bong sro-lanh uon tê?)
"""

KM_ORIGINAL = """1
00:00:01,000 --> 00:00:04,000
ខ្ញុំស្រលាញ់អ្នកណាស់

2
00:00:04,200 --> 00:00:07,000
បេះដូងខ្ញុំបែកបាក់
"""


def check(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(("  ✅ " if cond else "  ❌ ") + msg)


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def run():
    tmp = tempfile.mkdtemp(prefix="vida_lang_guard_")
    try:
        print("\n=== original-subtitle language guard ===\n")

        # --- Dominant-script detection -------------------------------------------------
        lang, conf = detect_text_language_ex(VI_SONG)
        check(lang == "vi" and conf, f"Vietnamese title detected ({lang}, confident={conf})")

        lang, conf = detect_text_language_ex(VI_VTT)
        check(lang == "vi" and conf,
              f"one Khmer line inside a Vietnamese caption does not flip it to km ({lang})")

        lang, conf = detect_text_language_ex(EN_SRT)
        check(lang == "en" and not conf,
              f"one stray 'tê' inside an English translation is not Vietnamese ({lang})")

        # --- Vietnamese song: translation must never be the original --------------------
        audio = os.path.join(tmp, VI_SONG + ".mp3")
        open(audio, "wb").write(b"\x00" * 256)
        write(os.path.join(tmp, VI_SONG + ".en.vtt"), VI_VTT)
        write(os.path.join(tmp, VI_SONG + ".en-tr.srt"), EN_SRT)       # new tag
        write(os.path.join(tmp, VI_SONG + ".en.srt"), EN_SRT)          # legacy tag

        picked = os.path.basename(find_matching_subtitles(audio) or "")
        check(picked.endswith(".en.vtt"),
              f"finder serves the Vietnamese caption, not the English track ({picked})")
        picked_vi = os.path.basename(find_matching_subtitles(audio, target_lang="vi") or "")
        check(picked_vi.endswith(".en.vtt"),
              f"explicit target vi also resolves to the Vietnamese caption ({picked_vi})")

        # Remove the real caption: the English tracks must NOT be served as the original.
        os.remove(os.path.join(tmp, VI_SONG + ".en.vtt"))
        picked_none = find_matching_subtitles(audio)
        check(picked_none is None,
              "no Vietnamese source left → finder returns None (ASR/LRCLIB) instead of English")

        # --- Khmer song: km-tr is a translation, km.srt is the original -----------------
        km_audio = os.path.join(tmp, "ស្រលាញ់អូន.mp3")
        open(km_audio, "wb").write(b"\x00" * 256)
        write(os.path.join(tmp, "ស្រលាញ់អូន.km-tr.srt"), KM_ORIGINAL)
        check(find_matching_subtitles(km_audio) is None,
              "a Khmer translation of a Khmer song is never used as the original")

        write(os.path.join(tmp, "ស្រលាញ់អូន.km.srt"), KM_ORIGINAL)
        picked_km = os.path.basename(find_matching_subtitles(km_audio) or "")
        check(picked_km.endswith(".km.srt"),
              f"the real Khmer cue sheet is still found ({picked_km})")

        # --- A re-sync must never overwrite a caption sheet holding different words ------
        from backend.app import _save_aligned_subtitles

        vi_srt_path = os.path.join(tmp, "capitao.mp3")
        open(vi_srt_path, "wb").write(b"\x00" * 128)
        human_srt = os.path.join(tmp, "capitao.srt")
        write(human_srt, EN_SRT)
        human_bytes = open(human_srt, "rb").read()

        vi_lyrics = [{"line_id": i, "start": 10.0 + i, "end": 12.0 + i, "text": t, "words": []}
                     for i, t in enumerate(["Hỡi ơi người ơi", "Em không cần tìm kiếm đâu xa",
                                            "Vì em biết là anh thương em nhất mà"])]
        _save_aligned_subtitles(vi_lyrics, vi_srt_path)
        check(open(human_srt, "rb").read() == human_bytes,
              "Vietnamese re-sync leaves the English caption .srt byte-identical")
        check(os.path.exists(os.path.join(tmp, "capitao.lrc")),
              "the studio .lrc cache is still written for the re-synced audio")

        same_words = [{"line_id": i, "start": 40.0 + i, "end": 42.0 + i, "text": t, "words": []}
                      for i, t in enumerate([
                          "Oh my dear, oh my dear",
                          "I don't need to search anywhere far",
                          "Because I know you love me the most by far",
                          "Oh my dear, oh my dear",
                          "We don't need to go anywhere else at all",
                          "Paradise is sitting at the bottom of a well with the one I adore",
                          "This love is as sweet as freshly squeezed orange juice",
                          "There's no way it can escape anyone's view",
                          "Do you love me? (Bong sro-lanh uon tê?)",
                      ])]
        _save_aligned_subtitles(same_words, os.path.join(tmp, "capitao.mp3"))
        refreshed = open(human_srt, encoding="utf-8").read()
        check("00:00:40,000" in refreshed and "00:00:10,760" not in refreshed,
              "an .srt carrying these same words is refreshed with the new timings")

        print(f"\n{len(PASS)} passed, {len(FAIL)} failed\n")
        for m in FAIL:
            print("FAILED: " + m)
        return 1 if FAIL else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(run())
