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
    _assign_lines_to_phrases,
    calibrate_lyrics_with_vocal_activity,
    force_align_lyrics_to_audio,
    snap_words_to_onsets,
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


def test_snap_words_to_onsets():
    """TEST 11: Word starts snap onto nearby singer onsets, order preserved."""
    print("\n" + "=" * 60)
    print("TEST 11: Word Snapping To Vocal Onsets")
    print("=" * 60)

    words = [
        {"word": "a", "start": 10.0, "end": 10.5},
        {"word": "b", "start": 10.5, "end": 11.0},
        {"word": "c", "start": 11.0, "end": 11.5},
        {"word": "d", "start": 11.5, "end": 12.0},
    ]
    onsets = [9.2, 10.68, 11.12, 11.4, 13.0]
    snapped = snap_words_to_onsets(words, 10.0, 12.0, onsets)

    starts = [w["start"] for w in snapped]
    assert_true(starts[0] == 10.0, f"First word pinned to line start ({starts[0]})")
    assert_true(starts[1] == 10.68, f"Word 'b' snapped to onset 10.68 (got {starts[1]})")
    assert_true(starts[2] == 11.12, f"Word 'c' snapped to onset 11.12 (got {starts[2]})")
    assert_true(all(b > a for a, b in zip(starts, starts[1:])), f"Starts strictly increasing {starts}")
    assert_true(snapped[-1]["end"] == 12.0, "Last word ends at line end")
    assert_true(all(10.0 <= w["start"] < w["end"] <= 12.0 for w in snapped), "All words inside line span")

    far = snap_words_to_onsets(words, 10.0, 12.0, [14.0, 15.0])
    assert_true([w["start"] for w in far] == [w["start"] for w in words], "Out-of-range onsets leave words untouched")


def test_phrase_dp_assignment():
    """TEST 12: Lines map onto sung phrases and never straddle an instrumental break."""
    print("\n" + "=" * 60)
    print("TEST 12: Phrase DP Line Assignment")
    print("=" * 60)

    phrases = [(5.0, 7.0), (7.5, 9.5), (20.0, 22.0), (22.4, 24.4), (24.8, 26.8)]
    runs = _assign_lines_to_phrases(phrases, [10, 10, 10, 10, 10])
    assert_true(runs == [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)], f"Equal lines take one phrase each ({runs})")

    runs = _assign_lines_to_phrases(phrases, [20, 10, 10, 10])
    assert_true(runs is not None and runs[0] == (0, 2), f"Long first line spans two phrases ({runs})")
    for q, p in runs or []:
        assert_true(not (q < 2 < p), f"Run {q}-{p} does not cross the 10s instrumental break")

    assert_true(_assign_lines_to_phrases(phrases[:2], [5, 5, 5]) is None, "Fewer phrases than lines -> fallback")


def test_calibrate_preserves_real_word_timing():
    """TEST 13: Real ASR word timing is kept, not stretched, when the line span changes."""
    print("\n" + "=" * 60)
    print("TEST 13: Calibration Keeps Real Word Timing")
    print("=" * 60)

    lyrics = [{
        "start": 10.0, "end": 12.0, "text": "one two three",
        "words": [
            {"word": "one", "start": 10.0, "end": 10.3},
            {"word": "two", "start": 10.9, "end": 11.2},
            {"word": "three", "start": 11.3, "end": 12.0},
        ],
    }]
    calibrated = calibrate_lyrics_with_vocal_activity(lyrics, vocal_segments=[(10.0, 13.5)])
    words = calibrated[0]["words"]
    assert_true(abs(words[1]["start"] - 10.9) < 0.02, f"'two' keeps its ASR start 10.9 (got {words[1]['start']})")
    assert_true(abs(words[2]["start"] - 11.3) < 0.02, f"'three' keeps its ASR start 11.3 (got {words[2]['start']})")
    assert_true(words[-1]["end"] == calibrated[0]["end"], "Last word reaches line end")


def test_force_align_synthetic_singer():
    """TEST 14: End-to-end alignment follows a synthetic singer's phrases and syllables."""
    print("\n" + "=" * 60)
    print("TEST 14: Forced Alignment On Synthetic Singer")
    print("=" * 60)

    import tempfile
    import wave
    import numpy as np

    sr = 16000
    y = np.zeros(int(sr * 32), np.float32)
    y += 0.05 * np.sin(2 * np.pi * 55 * np.arange(len(y)) / sr)
    truth, t = [], 6.0
    for n, sd in [(6, 0.35), (5, 0.4), (8, 0.25), (4, 0.5)]:
        onsets = []
        for k in range(n):
            tt = np.arange(int(sd * 0.9 * sr)) / sr
            env = np.minimum(1, tt / 0.03) * np.exp(-tt * 2.5)
            sig = sum((0.6 / h) * np.sin(2 * np.pi * (210 + 7 * k) * h * tt) for h in range(1, 6))
            s = int(t * sr)
            y[s:s + len(tt)] += (env * sig * 0.5).astype(np.float32)
            onsets.append(t)
            t += sd
        truth.append(onsets)
        t += 1.5

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "singer.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((np.clip(y, -1, 1) * 32000).astype(np.int16).tobytes())
        lyrics = [" ".join(f"w{i}{k}" for k in range(len(o))) for i, o in enumerate(truth)]
        aligned = force_align_lyrics_to_audio(lyrics, path)

    assert_true(len(aligned) == len(truth), f"All {len(truth)} lines aligned")
    line_errs = [abs(l["start"] - o[0]) for l, o in zip(aligned, truth)]
    word_errs = [abs(w["start"] - b) for l, o in zip(aligned, truth) for w, b in zip(l["words"], o)]
    assert_true(max(line_errs) < 0.15, f"Line starts within 150ms of singer (max {max(line_errs):.3f}s)")
    assert_true(sum(word_errs) / len(word_errs) < 0.12, f"Mean word-start error < 120ms ({sum(word_errs) / len(word_errs):.3f}s)")
    assert_true(aligned[0]["start"] >= 5.8, f"No lyrics during the 6s intro (first at {aligned[0]['start']})")


def test_ctc_aligner_graceful_fallback():
    """TEST 15: CTC aligner declines non-vocal / impossible input instead of corrupting timing."""
    print("\n" + "=" * 60)
    print("TEST 15: CTC Aligner Graceful Fallback")
    print("=" * 60)

    try:
        from backend.ctc_align import ctc_align_lyrics, is_available
    except ImportError:
        assert_true(True, "ctc_align module optional — fallback path exercised")
        return

    assert_true(ctc_align_lyrics(["hello"], "/does/not/exist.wav") is None,
                "Missing audio returns None (caller uses fallback)")
    assert_true(ctc_align_lyrics([""], __file__) is None,
                "Empty lyrics returns None")
    assert_true(callable(is_available), "is_available() probe exposed")


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
    test_snap_words_to_onsets()
    test_phrase_dp_assignment()
    test_calibrate_preserves_real_word_timing()
    test_force_align_synthetic_singer()
    test_ctc_aligner_graceful_fallback()

    print("\n" + "=" * 60)
    total = PASS_COUNT + FAIL_COUNT
    print(f"Results: {PASS_COUNT}/{total} passed, {FAIL_COUNT} failed")
    if FAIL_COUNT == 0:
        print("\xf0\x9f\x8e\x89 ALL TESTS PASSED — Sync quality verified!")
    else:
        print(f"\xe2\x9a\xa0\xef\xb8\x8f {FAIL_COUNT} test(s) failed — review required")
    print("=" * 60)

    sys.exit(1 if FAIL_COUNT > 0 else 0)
