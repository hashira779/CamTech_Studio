"""
Guards the post-alignment repairs in backend/sync_repair.py:

  - an unclear line in a repeated section takes its timing from its clearly heard twin
  - the repeat distance must be measured and agreed on, or nothing is touched
  - a clearly heard neighbour is never moved to make room
  - two lines repeated in a row are an echo, not a section, and are left alone
  - a line never stays on screen through an instrumental break
Run: python tests/test_sync_repair.py
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.sync_repair import close_word_gaps, end_lines_at_breaks, refit_to_voice, repair_from_repeats

PASS, FAIL = [], []


def check(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg)


def line(text, start, end, conf, n_words=3):
    """A line of n distinct words ("one-0 one-1 one-2"), evenly spread, each heard as clearly as the line."""
    step = (end - start) / n_words
    words = [{"word": f"{text}{k}", "start": round(start + k * step, 2), "end": round(start + (k + 1) * step, 2),
              "conf": conf} for k in range(n_words)]
    return {"text": " ".join(w["word"] for w in words), "start": start, "end": end, "confidence": conf, "words": words}


VERSE = ["one", "two", "three", "four", "five", "six"]
STARTS = [10.0, 13.0, 16.0, 19.0, 22.0, 25.0]
REPEAT = 100.0


def song(first_conf, second_conf, second_offset=REPEAT, jitter=None):
    """A verse sung twice, REPEAT seconds apart. jitter shifts single lines of the second copy."""
    out = [line(t, s, s + 2.5, c) for t, s, c in zip(VERSE, STARTS, first_conf)]
    for k, (t, s, c) in enumerate(zip(VERSE, STARTS, second_conf)):
        shift = second_offset + (jitter or {}).get(k, 0.0)
        out.append(line(t, s + shift, s + shift + 2.5, c))
    return out


def run():
    print("repeated sections")
    # line "three" in verse 1 was a wild guess; its twin in verse 2 was heard clearly
    lines = song([0.8, 0.8, 0.05, 0.8, 0.8, 0.8], [0.8] * 6)
    lines[2].update(start=17.4, end=18.6)
    n = repair_from_repeats(lines)
    check(n == 1, "exactly the one unclear line is repaired")
    check(abs(lines[2]["start"] - 16.0) < 0.01 and abs(lines[2]["end"] - 18.5) < 0.01,
          "it takes its twin's timing shifted back by the measured verse distance")
    check(lines[2]["timing_source"] == "repeat" and 0.4 <= lines[2]["confidence"] < 0.8,
          "it is labelled as borrowed and trusted a little less than its source")
    check(abs(lines[2]["words"][0]["start"] - 16.0) < 0.01, "its words move with it")

    # clear pairs disagree about the distance: it is not a reliable repeat, touch nothing
    lines = song([0.8, 0.8, 0.05, 0.8, 0.8, 0.8], [0.8] * 6, jitter={0: -2.0, 1: 1.5, 3: 3.0, 4: -1.0, 5: 2.2})
    before = copy.deepcopy(lines)
    check(repair_from_repeats(lines) == 0 and lines == before,
          "no repair when the clearly heard pairs disagree on the repeat distance")

    # the borrowed timing would push into a clearly heard neighbour: leave it
    lines = song([0.8, 0.8, 0.05, 0.8, 0.8, 0.8], [0.8] * 6)
    lines[1]["end"] = 17.0
    before_neighbour = copy.deepcopy(lines[1])
    repair_from_repeats(lines)
    check(lines[1] == before_neighbour and lines[2].get("timing_source") is None,
          "a clearly heard neighbour is never moved to make room")

    # the same neighbour, unclear this time, is trimmed instead
    lines = song([0.8, 0.1, 0.05, 0.8, 0.8, 0.8], [0.8, 0.3, 0.8, 0.8, 0.8, 0.8])
    lines[1]["end"] = 17.0
    repair_from_repeats(lines)
    check(lines[2].get("timing_source") == "repeat" and lines[1]["end"] <= lines[2]["start"] - 0.04,
          "an unclear neighbour is trimmed to make room")

    # a barely heard line borrows from a twin that is only moderately sure, but clearly surer
    lines = song([0.8, 0.8, 0.05, 0.8, 0.8, 0.8], [0.8, 0.8, 0.36, 0.8, 0.8, 0.8])
    lines[2].update(start=17.4, end=18.6)
    repair_from_repeats(lines)
    check(lines[2].get("timing_source") == "repeat" and abs(lines[2]["start"] - 16.0) < 0.01,
          "a 0.05 line takes its timing from a 0.36 twin")

    # two similar guesses: neither overrides the other
    lines = song([0.8, 0.8, 0.30, 0.8, 0.8, 0.8], [0.8, 0.8, 0.36, 0.8, 0.8, 0.8])
    lines[2].update(start=17.4, end=18.6)
    repair_from_repeats(lines)
    check(lines[2].get("timing_source") is None and lines[2]["start"] == 17.4,
          "a 0.30 line is not overridden by a 0.36 twin (not clearly surer)")

    # the second copy is short its last rows (an outro left out), so the repeat sits past half the song
    lines = song([0.8, 0.8, 0.05, 0.8, 0.8, 0.8], [0.8] * 6)
    lines[2].update(start=17.4, end=18.6)
    lines = [line("intro", 2.0, 4.0, 0.8)] + lines[:6] + lines[6:11]  # 1 + 6 + 5 rows: distance 6 > 12 // 2
    repair_from_repeats(lines)
    check(lines[3].get("timing_source") == "repeat" and abs(lines[3]["start"] - 16.0) < 0.01,
          "a repeat further apart than half the song is still used")

    # the two copies are broken into lines differently: verse 1 splits line "four" in two
    lines = song([0.8, 0.8, 0.05, 0.8, 0.8, 0.8], [0.8] * 6)
    lines[2].update(start=17.4, end=18.6)
    four = lines[3]
    a = {"text": "", "start": four["start"], "end": four["words"][1]["end"], "confidence": 0.8, "words": four["words"][:2]}
    b = {"text": "", "start": four["words"][2]["start"], "end": four["end"], "confidence": 0.8, "words": four["words"][2:]}
    lines = lines[:3] + [a, b] + lines[4:]
    repair_from_repeats(lines)
    check(lines[2].get("timing_source") == "repeat" and abs(lines[2]["start"] - 16.0) < 0.01,
          "twins are still found when the verses are broken into lines differently")

    # only two lines repeated back to back: an echo, not a section
    lines = [line("la", 10, 12, 0.8), line("lo", 12.1, 14, 0.05), line("la", 14.1, 16, 0.8),
             line("lo", 16.1, 18, 0.8), line("end", 18.1, 20, 0.8)]
    before = copy.deepcopy(lines)
    check(repair_from_repeats(lines) == 0 and lines == before, "a two-line echo is not treated as a section")

    print("lines on silence")
    voice = [(10.0, 13.0), (14.0, 16.0), (19.0, 20.0), (24.0, 27.0)]
    anchor_a = line("intro", 10.0, 13.0, 0.8)
    lost = line("lost", 16.5, 19.0, 0.1)  # sits in the 16-19 s silence
    anchor_b = line("after", 24.0, 27.0, 0.8)
    lines = [anchor_a, lost, anchor_b]
    before_a, before_b = dict(anchor_a), dict(anchor_b)
    n = refit_to_voice(lines, voice)
    check(n == 1 and lines[1]["start"] == 14.0, "a line sitting on silence moves onto the sung phrase after its neighbour")
    check(lines[0] == before_a and lines[2] == before_b, "clearly heard lines are never moved")

    lines = [line("intro", 10.0, 13.0, 0.8), line("sung", 14.0, 16.0, 0.1), line("after", 24.0, 27.0, 0.8)]
    check(refit_to_voice(lines, voice) == 0, "an unsure line already on the singing is left alone")

    doubled = {"text": "ទៅណាមកណា ទៅណាមកណា", "start": 16.5, "end": 19.0, "confidence": 0.1,
               "words": [{"word": w, "start": 16.5, "end": 19.0} for w in ["ទៅ", "ណា", "មក", "ណា"] * 2]}
    lines = [line("intro", 10.0, 13.0, 0.8), doubled, line("after", 24.0, 27.0, 0.8)]
    refit_to_voice(lines, voice)
    ws = lines[1]["words"]
    check(lines[1]["start"] == 14.0 and lines[1]["end"] >= 19.0,
          "a doubled row sung as two phrases stays on screen through both")
    check(all(w["start"] < 16.5 for w in ws[:4]) and all(w["start"] >= 19.0 for w in ws[4:]),
          "its first half is timed on the first phrase and its second half on the second")

    # Old recordings: the aligner is only fairly sure of most lines (0.3-0.45), and the voice
    # detector cuts the echoing singing into back-to-back pieces. A fairly sure line is an anchor:
    # the refit moves only the lost line next to it, never the whole stretch onto those pieces.
    chopped = [(10.0, 12.2), (12.2, 14.1), (14.1, 16.4), (16.4, 18.0), (18.0, 20.3), (20.3, 23.0), (24.0, 27.0)]
    lines = [line("intro", 10.0, 12.0, 0.8), line("fairly sure", 13.0, 17.0, 0.35), line("lost", 23.05, 23.95, 0.1),
             line("after", 24.0, 27.0, 0.8)]  # "lost" sits on the one real pause, which triggers the refit
    before = copy.deepcopy(lines)
    refit_to_voice(lines, chopped)
    check(lines[1] == before[1], "a line the aligner was fairly sure of (0.35) is never moved")

    print("a stray word far after its line")
    # កំពង់ធំជំរុំចិត្ត: "រូបពៅឲខ្ញុំ ជាគូ" sung at 130-136 s, its closing "អើយ" found at 159 s after
    # the solo, so the caption stayed up through the whole solo.
    stray = {"text": "រូបពៅឲខ្ញុំ ជាគូអើយ", "start": 129.98, "end": 170.85, "confidence": 0.63, "words": [
        {"word": "រូប", "start": 129.98, "end": 130.9}, {"word": "ពៅ", "start": 130.9, "end": 131.38},
        {"word": "ឲ", "start": 131.38, "end": 132.66}, {"word": "ខ្ញុំ", "start": 132.66, "end": 134.2},
        {"word": "ជា", "start": 134.26, "end": 134.78}, {"word": "គូ", "start": 134.78, "end": 136.26},
        {"word": "អើយ", "start": 159.14, "end": 170.85}]}
    lines = [stray, line("next", 170.9, 175.2, 0.7)]
    n = close_word_gaps(lines)
    w = lines[0]["words"]
    check(n == 1 and w[-1]["start"] == 136.26 and w[-1]["end"] <= 137.5,
          "the stray word moves to right after the word before it")
    check(lines[0]["end"] < 138.0, "the line ends with its singing instead of through the solo")
    check(lines[1]["start"] == 170.9, "the next line is untouched")
    held = line("held note", 10.0, 16.0, 0.7)
    held["words"][-1]["end"] = 16.0  # one long held word, no gap
    check(close_word_gaps([held]) == 0, "a long held word is not a gap")

    # ថ្នមចិត្ត: the first word "ថ្នម" stretched over the music before its line (92-112 s).
    stretched = {"text": "ថ្នម អើយថ្នម ឱ្យស្រីឆ្លើយ", "start": 92.38, "end": 126.61, "confidence": 0.42, "words": [
        {"word": "ថ្នម", "start": 92.38, "end": 112.04}, {"word": "អើយ", "start": 112.04, "end": 118.94},
        {"word": "ថ្នម", "start": 118.94, "end": 121.86}, {"word": "ឱ្យ", "start": 121.86, "end": 125.12},
        {"word": "ស្រី", "start": 125.12, "end": 125.48}, {"word": "ឆ្លើយ", "start": 125.48, "end": 126.61}]}
    lines = [line("before", 82.6, 87.4, 0.5), stretched, line("after", 129.1, 136.2, 0.6)]
    check(close_word_gaps(lines) == 1 and abs(lines[1]["start"] - 110.84) < 0.01,
          "a first word stretched over the music before its line starts the line where it is sung")
    check(lines[1]["words"][1]["start"] == 112.04 and lines[1]["end"] == 126.61, "the rest of the line is unchanged")
    long_end = line("long end", 50.0, 70.0, 0.6)
    long_end["words"][-1]["start"], long_end["words"][-1]["end"] = 55.0, 70.0
    close_word_gaps([long_end])
    check(long_end["words"][-1]["end"] == 61.0 and long_end["end"] <= 61.5, "a last word held past 6 s is cut at 6 s")

    print("instrumental breaks")
    voice = [(10.0, 20.0), (48.0, 60.0)]
    lines = [line("last of verse", 17.0, 47.5, 0.3), line("next verse", 48.2, 51.0, 0.8)]
    n = end_lines_at_breaks(lines, voice)
    check(n == 1 and abs(lines[0]["end"] - 20.4) < 0.01, "a line ends just after the voice stops before a break")
    check(all(17.0 <= w["start"] <= w["end"] <= 20.4 for w in lines[0]["words"]),
          "its words are squeezed inside the sung part")
    check(lines[1]["start"] == 48.2 and lines[1]["end"] == 51.0, "the line after the break is untouched")

    lines = [line("breath", 17.0, 22.0, 0.8)]
    check(end_lines_at_breaks(lines, [(10.0, 20.0), (21.0, 30.0)]) == 0, "a short breath is not a break")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed\n")
    for m in FAIL:
        print("FAILED: " + m)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(run())
