"""
End-to-end checks for the second (translated) lyric track:
  - translated SRT is stored as a SEPARATE companion file with the ORIGINAL timestamps
  - the original .srt is never overwritten
  - 'translation_only' display mode builds a display-only cue copy (originals untouched)
Run: python tests/test_translation_track.py
"""
import asyncio
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import (
    TranslationSaveRequest,
    build_translation_display_lyrics,
    save_translation_api,
    get_translation_api,
    list_translations_api,
)
from backend.lyric_engine import parse_subtitle_file

PASS, FAIL = [], []
res = asyncio.run


def check(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(("  ✅ " if cond else "  ❌ ") + msg)


def run():
    tmp = tempfile.mkdtemp(prefix="vida_tr_")
    try:
        audio = os.path.join(tmp, "demo_song.mp3")
        with open(audio, "wb") as f:
            f.write(b"\x00" * 1024)

        original_srt = os.path.join(tmp, "demo_song.srt")
        with open(original_srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:04,000\nខ្ញុំស្រលាញ់អ្នកណាស់\n\n"
                    "2\n00:00:04,200 --> 00:00:07,000\nបេះដូងខ្ញុំបែកបាក់\n\n")
        original_bytes = open(original_srt, "rb").read()

        lyrics_data = [
            {"line_id": 0, "start": 1.0, "end": 4.0, "text": "ខ្ញុំស្រលាញ់អ្នកណាស់"},
            {"line_id": 1, "start": 4.2, "end": 7.0, "text": "បេះដូងខ្ញុំបែកបាក់"},
        ]

        print("\n=== VIDA translated lyric track (storage + display modes) ===\n")

        # 1) Save writes only <base>.<lang>-tr.srt
        req = TranslationSaveRequest(audio_path=audio, lang="en",
                                     lines=["I love you so much", "My heart is broken"],
                                     lyrics_data=lyrics_data)
        out = res(save_translation_api(req))
        companion = os.path.join(tmp, "demo_song.en-tr.srt")
        check(out["status"] == "success" and out["count"] == 2, f"save returned {out['status']} / {out['count']} cues")
        check(os.path.exists(companion), "translated track saved as separate file demo_song.en-tr.srt")
        check(not os.path.exists(os.path.join(tmp, "demo_song.en.srt")),
              "translation never occupies the plain .en.srt original slot")
        check(open(original_srt, "rb").read() == original_bytes, "original demo_song.srt left byte-identical")
        check(os.path.basename(out["file"]) == "demo_song.en-tr.srt", f"reported file = {os.path.basename(out['file'])}")

        # 2) Timestamps reused verbatim from the original cues
        cues = parse_subtitle_file(companion)
        check(len(cues) == 2, f"companion SRT parsed back: {len(cues)} cues")
        check(abs(cues[0]["start"] - 1.0) < 0.02 and abs(cues[0]["end"] - 4.0) < 0.02,
              f"cue 1 timings reused from original ({cues[0]['start']}s → {cues[0]['end']}s)")
        check(abs(cues[1]["start"] - 4.2) < 0.02 and abs(cues[1]["end"] - 7.0) < 0.02,
              f"cue 2 timings reused from original ({cues[1]['start']}s → {cues[1]['end']}s)")
        check(cues[0]["text"].strip() == "I love you so much", "translated text stored verbatim")

        # 3) Loader returns lines + cues for 1:1 index remapping
        got = res(get_translation_api(audio_path=audio, lang="en"))
        check(got["status"] == "success" and len(got["lines"]) == 2, "GET /api/lyrics/translation returns both lines")
        check(len(got["cues"]) == 2 and abs(got["cues"][0]["start"] - 1.0) < 0.02,
              "GET returns cue timings so the frontend can remap by timestamp")

        langs = res(list_translations_api(audio_path=audio))
        check("en" in langs["langs"], f"list shows available tracks: {langs['langs']}")
        check("km" not in langs["langs"], "original .km/.srt never listed as a translation")

        # 4) Empty translated line keeps index alignment
        req2 = TranslationSaveRequest(audio_path=audio, lang="th",
                                      lines=["", "哈心碎"], lyrics_data=lyrics_data)
        out2 = res(save_translation_api(req2))
        cues2 = parse_subtitle_file(os.path.join(tmp, "demo_song.th-tr.srt"))
        check(len(cues2) == 1 and abs(cues2[0]["start"] - 4.2) < 0.02,
              f"blank line skipped but index 2 keeps its own original timing ({cues2[0]['start']}s)")

        # 5) translation_only display copy — originals strictly untouched
        src = [dict(l, words=[{"word": "ខ្ញុំ", "start": 1.0, "end": 1.5}]) for l in lyrics_data]
        snapshot = repr(src)
        display = build_translation_display_lyrics(src, "translation_only", ["I love you so much", "My heart is broken"])
        check(repr(src) == snapshot, "build_translation_display_lyrics never mutates the source cues")
        check(display is not src and display[0]["text"] == "I love you so much",
              "translation_only renderer receives translated text with word timings")
        check(len(display[0]["words"]) > 1 and all(w["start"] >= 1.0 and w["end"] <= 4.0 for w in display[0]["words"]),
              f"re-timed words stay inside the original {src[0]['start']}–{src[0]['end']}s window")
        check(build_translation_display_lyrics(src, "bilingual", ["x", "y"]) is src,
              "bilingual mode leaves the cue list untouched (subline is drawn separately)")
        check(build_translation_display_lyrics(src, "original_only", None) is src,
              "original_only mode is a no-op — default behaviour preserved")

        # 6) Missing translation for a line falls back to the original text
        part = build_translation_display_lyrics(src, "translation_only", ["", "My heart is broken"])
        check(part[0]["text"] == src[0]["text"], "line without a translation keeps showing the original (never blank)")

        # 7) Khmer as a TARGET must never collide with the original "<song>.km.srt" convention
        km_original = os.path.join(tmp, "demo_song.km.srt")
        with open(km_original, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:04,000\nខ្ញុំស្រលាញ់អ្នកណាស់\n\n"
                    "2\n00:00:04,200 --> 00:00:07,000\nបេះដូងខ្ញុំបែកបាក់\n\n")
        km_original_bytes = open(km_original, "rb").read()

        # Canonical spelling on purpose: export_subtitles_to_srt runs the Khmer
        # proper-spelling corrector, so a misspelled input would come back normalized.
        km_lines = ["បងស្រឡាញ់ណាស់", "បេះដូងបែកបាក់ហើយ"]
        out_km = res(save_translation_api(TranslationSaveRequest(
            audio_path=audio, lang="km", lines=km_lines, lyrics_data=lyrics_data)))
        check(out_km["status"] == "success" and out_km["file"].endswith("demo_song.km-tr.srt"),
              f"Khmer track saved under its own tag ({os.path.basename(out_km['file'])})")
        check(open(km_original, "rb").read() == km_original_bytes,
              "existing <song>.km.srt (original Khmer cues) left byte-identical")
        check(open(original_srt, "rb").read() == original_bytes,
              "<song>.srt still byte-identical after a Khmer save")

        got_km = res(get_translation_api(audio_path=audio, lang="km"))
        check(got_km["lines"] == km_lines, "GET ?lang=km reads back the Khmer translation lines")
        check([c["start"] for c in got_km["cues"]] == [1.0, 4.2],
              "Khmer track reuses the original cue start times")

        langs = res(list_translations_api(audio_path=audio))["langs"]
        check("km" in langs, f"list maps the km-tr file back to lang code 'km' ({langs})")
        check("en" in langs, f"list still reports the English track alongside it ({langs})")
        check("km-tr" not in langs, f"list never leaks the raw file tag ({langs})")

        print(f"\n{len(PASS)} passed, {len(FAIL)} failed\n")
        if FAIL:
            for m in FAIL:
                print("FAILED: " + m)
        return 1 if FAIL else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(run())
