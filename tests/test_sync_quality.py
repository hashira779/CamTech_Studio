"""
Comprehensive Sync Quality Test Suite for VIDA Singer-Lyrics Alignment.

Validates:
1. Monotonic non-overlapping line timestamps
2. Proportional duration clamping (no hard 4.5s chop)
3. Syllable-weighted word redistribution (no equal distribution)
4. Word timestamps clamped within line boundaries
5. Anti-cascading pass preserves timing integrity
6. End-to-end forced alignment pipeline
7. Double-check verification guarantees
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.lyric_engine import (
    double_check_lyrics,
    tokenize_line_words,
    compute_weighted_word_timestamps,
    parse_subtitle_content,
    clean_subtitle_text,
    normalize_khmer_orthography,
)
from backend.vocal_align import (
    _interpolate_words_simple,
    calibrate_lyrics_with_vocal_activity,
)

PASS_COUNT = 0
FAIL_COUNT = 0


def assert_true(condition, msg):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  ✅ {msg}")
    else:
        FAIL_COUNT += 1
        print(f"  ❌ FAIL: {msg}")


def test_monotonic_non_overlapping():
    """TEST 1: double_check_lyrics guarantees strictly monotonic, non-overlapping timestamps."""
    print("\n" + "=" * 60)
    print("TEST 1: Monotonic Non-Overlapping Timestamps")
    print("=" * 60)

    lyrics = [
        {"start": 5.0, "end": 8.0, "text": "First line of song"},
        {"start": 7.5, "end": 10.0, "text": "Second line overlaps"},
        {"start": 9.0, "end": 12.0, "text": "Third line"},
        {"start": 11.5, "end": 14.0, "text": "Fourth line"},
    ]

    verified, report = double_check_lyrics(lyrics)

    assert_true(report["verified"] is True, "Report should be verified")
    assert_true(len(verified) == 4, f"All 4 lines preserved (got {len(verified)})")

    for i in range(1, len(verified)):
        prev = verified[i - 1]
        curr = verified[i]
        assert_true(
            curr["start"] >= prev["end"],
            f"Line {i} start ({curr['start']}) >= Line {i-1} end ({prev['end']})"
        )
        assert_true(
            curr["start"] >= 0,
            f"Line {i} start ({curr['start']}) >= 0"
        )


def test_word_timestamps_within_line_bounds():
    """TEST 2: Word timestamps are clamped within their parent line boundaries."""
    print("\n" + "=" * 60)
    print("TEST 2: Word Timestamps Clamped Within Line Bounds")
    print("=" * 60)

    lyrics = [
        {
            "start": 5.0, "end": 8.0, "text": "Hello beautiful world",
            "words": [
                {"word": "Hello", "start": 5.0, "end": 6.5},
                {"word": "beautiful", "start": 6.5, "end": 8.5},
                {"word": "world", "start": 8.5, "end": 9.5},
            ]
        },
        {"start": 9.0, "end": 12.0, "text": "Second line here"},
    ]

    verified, report = double_check_lyrics(lyrics)

    assert_true(len(verified) >= 1, "At least 1 line preserved")

    line0 = verified[0]
    for w in line0.get("words", []):
        assert_true(
            w["end"] <= line0["end"] + 0.01,
            f"Word '{w['word']}' end ({w['end']}) <= line end ({line0['end']})"
        )

    if len(verified) >= 2:
        assert_true(
            verified[1]["start"] >= verified[0]["end"],
            f"Line 2 start ({verified[1]['start']}) >= Line 1 end ({verified[0]['end']}) — no cascading overlap"
        )


def test_proportional_duration_clamping():
    """TEST 3: Long sustained phrases get proportional scaling, not hard 4.5s chop."""
    print("\n" + "=" * 60)
    print("TEST 3: Proportional Duration Clamping")
    print("=" * 60)

    words = _interpolate_words_simple("This is a long sustained singing phrase", 0.0, 10.0)

    total_dur = words[-1]["end"] - words[0]["start"]
    assert_true(total_dur > 4.5, f"Total word span ({total_dur:.2f}s) > 4.5s (not hard-chopped)")
    assert_true(total_dur <= 10.0, f"Total word span ({total_dur:.2f}s) <= 10.0s (original)")

    assert_true(
        words[0]["start"] == 0.0,
        f"First word starts at 0.0 (got {words[0]['start']})"
    )


def test_syllable_weighted_word_distribution():
    """TEST 4: Word timestamps use syllable-weighted distribution, not equal."""
    print("\n" + "=" * 60)
    print("TEST 4: Syllable-Weighted Word Distribution")
    print("=" * 60)

    words = compute_weighted_word_timestamps(
        ["I", "absolutely", "love", "everything"],
        start_time=0.0,
        end_time=4.0
    )

    assert_true(len(words) == 4, f"4 words returned (got {len(words)})")

    dur_i = words[0]["end"] - words[0]["start"]
    dur_abs = words[1]["end"] - words[1]["start"]
    assert_true(
        dur_abs > dur_i,
        f"'absolutely' ({dur_abs:.2f}s) > 'I' ({dur_i:.2f}s) — syllable weighting works"
    )

    dur_last = words[3]["end"] - words[3]["start"]
    dur_third = words[2]["end"] - words[2]["start"]
    assert_true(
        dur_last >= dur_third * 0.9,
        f"Last word '{words[3]['word']}' ({dur_last:.2f}s) has cadence extension"
    )


def test_khmer_syllable_weighted_distribution():
    """TEST 5: Khmer word timestamps use syllable-weighted distribution."""
    print("\n" + "=" * 60)
    print("TEST 5: Khmer Syllable-Weighted Distribution")
    print("=" * 60)

    khmer_words = tokenize_line_words("\u1794\u1784\u179f\u17d2\u179a\u17a1\u17b6\u1789\u17cb\u17a2\u17bc\u1793")
    assert_true(len(khmer_words) >= 1, f"Khmer tokenized into {len(khmer_words)} tokens")

    words = compute_weighted_word_timestamps(khmer_words, 0.0, 3.0)
    assert_true(len(words) == len(khmer_words), f"All tokens timestamped")

    for w in words:
        assert_true(
            0.0 <= w["start"] < w["end"] <= 3.0,
            f"Khmer word '{w['word']}' in bounds [{w['start']}, {w['end']}]"
        )


def test_anti_cascading_preserves_weights():
    """TEST 6: Anti-cascading pass preserves syllable-weighted word timing."""
    print("\n" + "=" * 60)
    print("TEST 6: Anti-Cascading Preserves Syllable Weights")
    print("=" * 60)

    lyrics = [
        {
            "line_id": 0, "start": 5.0, "end": 9.0,
            "text": "I love you forever",
            "words": [
                {"word": "I", "start": 5.0, "end": 5.8},
                {"word": "love", "start": 5.8, "end": 6.8},
                {"word": "you", "start": 6.8, "end": 7.5},
                {"word": "forever", "start": 7.5, "end": 9.0},
            ]
        },
        {
            "line_id": 1, "start": 8.5, "end": 12.0,
            "text": "I absolutely love everything",
            "words": [
                {"word": "I", "start": 8.5, "end": 9.0},
                {"word": "absolutely", "start": 9.0, "end": 10.5},
                {"word": "love", "start": 10.5, "end": 11.0},
                {"word": "everything", "start": 11.0, "end": 12.0},
            ]
        }
    ]

    calibrated = calibrate_lyrics_with_vocal_activity(lyrics, vocal_segments=None)

    assert_true(len(calibrated) == 2, "Both lines preserved")

    line2 = calibrated[1]
    if line2.get("words") and len(line2["words"]) >= 4:
        dur_i = line2["words"][0]["end"] - line2["words"][0]["start"]
        dur_abs = line2["words"][1]["end"] - line2["words"][1]["start"]
        assert_true(
            dur_abs > dur_i * 1.1,
            f"After anti-cascade: 'absolutely' ({dur_abs:.2f}s) > 'I' ({dur_i:.2f}s) — weights preserved"
        )


def test_lrc_parsing_and_verification():
    """TEST 7: LRC parsing produces verified, monotonic, word-timestamped output."""
    print("\n" + "=" * 60)
    print("TEST 7: LRC Parsing & Verification Pipeline")
    print("=" * 60)

    lrc = """[ti:Test Song]
[ar:Test Artist]
[00:05.00]First line of the beautiful song
[00:10.50]Second line with more words to sing along
[00:15.80]Third and final line ends here
"""

    parsed = parse_subtitle_content(lrc)
    assert_true(len(parsed) == 3, f"3 lines parsed (got {len(parsed)})")

    for i, line in enumerate(parsed):
        assert_true(
            line.get("words") and len(line["words"]) > 0,
            f"Line {i+1} has word-level timestamps ({len(line.get('words', []))} words)"
        )
        assert_true(
            line["end"] > line["start"],
            f"Line {i+1} has positive duration ({line['start']} -> {line['end']})"
        )

    for i in range(1, len(parsed)):
        assert_true(
            parsed[i]["start"] >= parsed[i-1]["start"],
            f"Line {i+1} start >= Line {i} start (monotonic)"
        )


def test_srt_parsing_with_overlaps():
    """TEST 8: SRT parsing handles overlapping cues gracefully."""
    print("\n" + "=" * 60)
    print("TEST 8: SRT Parsing With Overlapping Cues")
    print("=" * 60)

    srt = """1
00:00:05,000 --> 00:00:08,500
First singing line

2
00:00:07,800 --> 00:00:11,000
Second line starts before first ends

3
00:00:10,500 --> 00:00:14,000
Third line also overlaps
"""

    parsed = parse_subtitle_content(srt)
    assert_true(len(parsed) >= 2, f"At least 2 lines parsed (got {len(parsed)})")

    for i in range(1, len(parsed)):
        assert_true(
            parsed[i]["start"] >= parsed[i-1]["end"] - 0.05,
            f"Line {i+1} doesn't heavily overlap line {i}"
        )


def test_empty_and_edge_cases():
    """TEST 9: Edge cases — empty input, single line, no words."""
    print("\n" + "=" * 60)
    print("TEST 9: Edge Cases & Boundary Conditions")
    print("=" * 60)

    v, r = double_check_lyrics([])
    assert_true(len(v) == 0, "Empty input returns empty output")
    assert_true(r["verified"] is True, "Empty input is verified")

    v, r = double_check_lyrics([{"start": 0, "end": 3, "text": "Solo line"}])
    assert_true(len(v) == 1, "Single line preserved")
    assert_true(v[0]["words"] and len(v[0]["words"]) > 0, "Single line gets words")

    v, r = double_check_lyrics([
        {"start": 0, "end": 3, "text": "Real line"},
        {"start": 4, "end": 7, "text": ""},
        {"start": 8, "end": 11, "text": "[music]"},
    ])
    assert_true(len(v) == 1, f"Only real line kept (got {len(v)} lines)")


def test_interpolate_words_simple_delegates():
    """TEST 10: _interpolate_words_simple uses syllable-weighted engine."""
    print("\n" + "=" * 60)
    print("TEST 10: Word Interpolation Delegates to Weighted Engine")
    print("=" * 60)

    words = _interpolate_words_simple("I absolutely love everything", 0.0, 4.0)
    assert_true(len(words) >= 3, f"Multiple words returned ({len(words)})")

    durs = [(w["word"], w["end"] - w["start"]) for w in words]
    short_words = [d for w, d in durs if len(w) <= 2]
    long_words = [d for w, d in durs if len(w) >= 6]

    if short_words and long_words:
        avg_short = sum(short_words) / len(short_words)
        avg_long = sum(long_words) / len(long_words)
        assert_true(
            avg_long > avg_short,
            f"Long words ({avg_long:.2f}s avg) > short words ({avg_short:.2f}s avg)"
        )


if __name__ == "__main__":
    print("\xf0\x9f\x8e\xa4 VIDA Sync Quality Test Suite")
    print("=" * 60)

    test_monotonic_non_overlapping()
    test_word_timestamps_within_line_bounds()
    test_proportional_duration_clamping()
    test_syllable_weighted_word_distribution()
    test_khmer_syllable_weighted_distribution()
    test_anti_cascading_preserves_weights()
    test_lrc_parsing_and_verification()
    test_srt_parsing_with_overlaps()
    test_empty_and_edge_cases()
    test_interpolate_words_simple_delegates()

    print("\n" + "=" * 60)
    total = PASS_COUNT + FAIL_COUNT
    print(f"Results: {PASS_COUNT}/{total} passed, {FAIL_COUNT} failed")
    if FAIL_COUNT == 0:
        print("\xf0\x9f\x8e\x89 ALL TESTS PASSED — Sync quality verified!")
    else:
        print(f"\xe2\x9a\xa0\xef\xb8\x8f {FAIL_COUNT} test(s) failed — review required")
    print("=" * 60)

    sys.exit(1 if FAIL_COUNT > 0 else 0)
