"""
Corrections applied after word alignment, using what the song itself tells us.

1. Repeated sections. A second verse or chorus is sung to the same music as the first, so its
   words sit a fixed time after their twins. That distance is measured from the words the
   aligner heard clearly; a line it could not hear then takes its timing from its clearly heard
   twin words, shifted by that distance. Twins are matched word by word, so it works however
   the lyrics were broken into lines (one verse split "ទៅណាមកណា / ទៅណាមកណា", the other not).
2. Lines on silence. A line that sits mostly where nobody sings is re-placed, with the unsure
   lines around it, onto the sung phrases between its clearly heard neighbours.
3. Instrumental breaks. A line may not stay on screen through a stretch with no voice: it ends
   shortly after the singing it belongs to stops.

Lines are dicts with start, end, text, confidence and words [{word, start, end, conf}].
"""

import logging
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

Line = Dict[str, Any]

# A repeated section is at least this many consecutive identical words; a twin pair only
# counts inside a run of at least MIN_RUN_WORDS, so a lone common word ("បង") is never a twin.
MIN_SECTION_WORDS = 8
MIN_RUN_WORDS = 4
# Clear word pairs needed to trust the measured distance, and how much they may disagree.
MIN_CLEAR_PAIRS = 5
MAX_SPREAD_S = 0.35
# Pairs used to MEASURE the repeat distance must both be clearly heard.
CLEAR = 0.5
# A line below UNCLEAR may borrow its twin's timing when the twin is TRUSTED and clearly more
# confident than it (by MARGIN). Lines at 0.3-0.4 sat within 0.5 s of their twin 89% of the time
# on 154 measured pairs, so a 0.3 twin is a far better guess than a 0.05 line.
UNCLEAR = 0.4
TRUSTED = 0.3
MARGIN = 0.15
# A borrowed timing is trusted a bit less than the measurement it came from.
BORROWED_TRUST = 0.9

# Silence long enough to be an instrumental part rather than a breath.
MIN_BREAK_S = 2.5
# How long a line may linger after the voice stops.
LINGER_S = 0.4


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", str(text), flags=re.UNICODE).lower()


def _flat_words(lines: List[Line]) -> List[Dict[str, Any]]:
    """Every word of the song in order, with its line, key, timing and how clearly it was heard."""
    out = []
    for li, line in enumerate(lines):
        for wi, w in enumerate(line.get("words") or []):
            key = _norm(w.get("word", ""))
            if key:
                out.append({"li": li, "wi": wi, "key": key, "start": w["start"], "end": w["end"],
                            "conf": float(w.get("conf", line.get("confidence", 0)))})
    return out


def _runs(keys: List[str], d: int) -> List[Tuple[int, int]]:
    """Runs of consecutive i where word i and word i+d are the same word."""
    runs: List[Tuple[int, int]] = []
    start = None
    for i in range(len(keys) - d + 1):
        same = i < len(keys) - d and keys[i] == keys[i + d]
        if same and start is None:
            start = i
        elif not same and start is not None:
            runs.append((start, i - 1))
            start = None
    return runs


def _sections(words: List[Dict[str, Any]]) -> List[Tuple[int, float, float, set]]:
    """
    (word distance, time distance, spread, word indexes paired inside a run) for every repeated
    section whose clearly heard word pairs agree on one time distance.
    """
    keys = [w["key"] for w in words]
    n = len(keys)
    found = []
    # A repeat can sit just past half the song (an outro left out, or a short last verse).
    for d in range(1, n - MIN_SECTION_WORDS + 1):
        runs = [(a, b) for a, b in _runs(keys, d) if b - a + 1 >= MIN_RUN_WORDS]
        if not runs or max(b - a + 1 for a, b in runs) < MIN_SECTION_WORDS:
            continue
        paired = {i for a, b in runs for i in range(a, b + 1)}
        deltas = [words[i + d]["start"] - words[i]["start"] for i in paired
                  if words[i]["conf"] >= CLEAR and words[i + d]["conf"] >= CLEAR]
        if len(deltas) < MIN_CLEAR_PAIRS:
            continue
        mid = statistics.median(deltas)
        close = [x for x in deltas if abs(x - mid) <= MAX_SPREAD_S]
        if len(close) < MIN_CLEAR_PAIRS:
            continue
        found.append((d, statistics.median(close), max(abs(x - mid) for x in close), paired))
    return found


def _make_room(lines: List[Line], idx: int, moved: Dict[str, Any]) -> bool:
    """
    Whether the borrowed timing fits at idx. A clearly heard neighbour is never moved; an unclear
    one (its timing was a guess) is trimmed to make room, as long as it keeps a singable length.
    """
    gap, min_len = 0.05, 0.6
    prev = lines[idx - 1] if idx > 0 else None
    nxt = lines[idx + 1] if idx + 1 < len(lines) else None
    trims = []
    if prev and moved["start"] < prev["end"] - gap:
        if prev.get("confidence", 0) >= UNCLEAR or moved["start"] - gap - prev["start"] < min_len:
            return False
        trims.append((prev, "end", moved["start"] - gap))
    if nxt and moved["end"] > nxt["start"] + gap:
        if nxt.get("confidence", 0) >= UNCLEAR or nxt["end"] - (moved["end"] + gap) < min_len:
            return False
        trims.append((nxt, "start", moved["end"] + gap))
    for line, edge, t in trims:
        old_start, old_end = line["start"], line["end"]
        line[edge] = round(t, 2)
        scale = (line["end"] - line["start"]) / (old_end - old_start) if old_end > old_start else 1.0
        for w in line.get("words", []):
            w["start"] = round(line["start"] + (w["start"] - old_start) * scale, 2)
            w["end"] = round(line["start"] + (w["end"] - old_start) * scale, 2)
    return True


def _twin_timings(lines: List[Line], li: int, words: List[Dict[str, Any]],
                  sections) -> List[Tuple[float, Dict[str, Any]]]:
    """
    Every clearly heard twin timing for line li, surest first, as (twin confidence, moved line).
    A line can have several (verse 2, a chorus, an outro); if the surest does not fit between its
    neighbours, the next one may.
    """
    mine = [k for k, w in enumerate(words) if w["li"] == li]
    if not mine or len(mine) != sum(1 for w in lines[li].get("words") or [] if _norm(w.get("word", ""))):
        return []
    own = lines[li].get("confidence", 0)
    found = []
    for d, delta, _spread, paired in sections:
        for direction in (1, -1):
            twins = []
            for k in mine:
                pair_at = k if direction == 1 else k - d  # pairs are indexed by their earlier word
                j = k + direction * d
                if not (0 <= j < len(words)) or pair_at not in paired or words[j]["key"] != words[k]["key"]:
                    break
                twins.append(j)
            else:
                twin_conf = sum(words[j]["conf"] for j in twins) / len(twins)
                if twin_conf < TRUSTED or twin_conf - own < MARGIN:
                    continue
                shift = -direction * delta
                by_index = {words[k]["wi"]: words[j] for k, j in zip(mine, twins)}
                new_words = []
                for wi, w in enumerate(lines[li]["words"]):
                    t = by_index.get(wi)
                    if t is None:
                        return []  # a word with nothing to match: leave the line alone
                    new_words.append({**w, "start": round(t["start"] + shift, 2), "end": round(t["end"] + shift, 2)})
                found.append((twin_conf, {"start": new_words[0]["start"], "end": new_words[-1]["end"], "words": new_words}))
    return sorted(found, key=lambda f: -f[0])


def repair_from_repeats(lines: List[Line], passes: int = 3) -> int:
    """Re-times unclear lines from their clearly heard twin words in a repeated section."""
    sections = _sections(_flat_words(lines))
    for d, delta, spread, _ in sections:
        log.info(f"[Sync Repair] Words repeat {d} apart, {delta:.2f}s later (±{spread:.2f}s)")
    if not sections:
        return 0
    repaired = set()
    # A repair can free the room another one needs, so go round a few times.
    for _ in range(passes):
        changed = 0
        for li, line in enumerate(lines):
            if li in repaired or line.get("confidence", 0) >= UNCLEAR:
                continue
            fitting = next(((c, m) for c, m in _twin_timings(lines, li, _flat_words(lines), sections)
                            if _make_room(lines, li, m)), None)
            if not fitting:
                continue
            twin_conf, moved = fitting
            line.update(moved)
            line["confidence"] = round(twin_conf * BORROWED_TRUST, 3)
            line["timing_source"] = "repeat"
            repaired.add(li)
            changed += 1
        if not changed:
            break
    return len(repaired)


def _breaks(vocal_segments: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    segs = sorted(vocal_segments)
    return [(segs[k][1], segs[k + 1][0]) for k in range(len(segs) - 1)
            if segs[k + 1][0] - segs[k][1] >= MIN_BREAK_S]


def _fit_words(line: Line, new_end: float) -> None:
    """Squeezes the line's words proportionally into [start, new_end]."""
    old_len = line["end"] - line["start"]
    scale = (new_end - line["start"]) / old_len if old_len > 0 else 1.0
    for w in line.get("words", []):
        w["start"] = round(line["start"] + (w["start"] - line["start"]) * scale, 2)
        w["end"] = round(line["start"] + (w["end"] - line["start"]) * scale, 2)
    line["end"] = round(new_end, 2)


def end_lines_at_breaks(lines: List[Line], vocal_segments: Optional[List[Tuple[float, float]]]) -> int:
    """Ends any line that runs on into an instrumental break shortly after the voice stops."""
    if not vocal_segments:
        return 0
    fixed = 0
    for line in lines:
        for gap_start, gap_end in _breaks(vocal_segments):
            sung_before_gap = gap_start - line["start"]
            runs_into_gap = line["end"] - gap_start
            if sung_before_gap >= 0.6 and runs_into_gap > LINGER_S + 0.5:
                _fit_words(line, gap_start + LINGER_S)
                fixed += 1
                break
    return fixed


# A clearly heard line always overlaps the singing: on 187 clearly heard lines across 8 songs none
# had less than 60% of its span voiced. A line below that sits mostly on silence and is misplaced
# (measured case: a borrowed "ទៅណាមកណា ទៅណាមកណា" landing 2 s late, on 22% voice).
MIN_VOICED = 0.6
# Lines at or above this confidence are anchors the refit never moves.
ANCHOR = 0.5


def _voiced(segs: List[Tuple[float, float]], a: float, b: float) -> float:
    """Share of [a, b] the singer is heard in."""
    if b <= a:
        return 0.0
    return sum(max(0.0, min(e, b) - max(s, a)) for s, e in segs) / (b - a)


def _time_words_on_phrases(line: Line, spans: List[Tuple[float, float]], time_line_words) -> List[Dict[str, Any]]:
    """
    Word timings for a line laid over sung phrases. A row that writes one phrase twice
    ("ទៅណាមកណា ទៅណាមកណា") sung as two phrases gets one half per phrase, so the karaoke sweep
    restarts with the singer; any other line is spread over its sung time.
    """
    words = [w.get("word", "") for w in line.get("words") or []]
    half = len(words) // 2
    doubled = half and len(words) % 2 == 0 and [_norm(w) for w in words[:half]] == [_norm(w) for w in words[half:]]
    if not (doubled and len(spans) >= 2):
        return time_line_words(line["text"], line["start"], line["end"], vocal_spans=spans)
    first_end = min(spans[0][1] + 0.25, spans[1][0] - 0.05)
    out = time_line_words(" ".join(words[:half]), line["start"], first_end, vocal_spans=spans[:1])
    out += time_line_words(" ".join(words[half:]), spans[1][0], line["end"], vocal_spans=spans[1:])
    return out


def refit_to_voice(lines: List[Line], vocal_segments: Optional[List[Tuple[float, float]]]) -> int:
    """
    Re-places a line that sits mostly on silence, with the uncertain lines around it, onto the
    sung phrases between its clearly heard neighbours, each line on a run of phrases matching its
    length. Kept only if the lines then overlap the singing more than before.
    """
    if not vocal_segments:
        return 0
    try:
        from backend.vocal_align import _assign_lines_to_phrases, time_line_words
    except ImportError:
        from vocal_align import _assign_lines_to_phrases, time_line_words
    segs = sorted((float(s), float(e)) for s, e in vocal_segments)
    n, fixed, i = len(lines), 0, 0
    while i < n:
        line = lines[i]
        if line.get("confidence", 0) >= ANCHOR or _voiced(segs, line["start"], line["end"]) >= MIN_VOICED:
            i += 1
            continue
        a, b = i, i + 1
        while a > 0 and lines[a - 1].get("confidence", 0) < ANCHOR:
            a -= 1
        while b < n and lines[b].get("confidence", 0) < ANCHOR:
            b += 1
        i = b
        lo = lines[a - 1]["end"] + 0.05 if a > 0 else max(0.0, lines[a]["start"] - 3.0)
        hi = lines[b]["start"] - 0.05 if b < n else lines[b - 1]["end"] + 3.0
        phrases = [(max(s, lo), min(e, hi)) for s, e in segs if min(e, hi) - max(s, lo) > 0.15]
        weights = [float(max(4, len(_norm(l["text"])))) for l in lines[a:b]]
        runs = _assign_lines_to_phrases(phrases, weights) if len(phrases) >= b - a else None
        if not runs:
            continue
        placed = []
        for off, (q, p) in enumerate(runs):
            # A phrase the fitter left without a line (the second "ទៅណាមកណា" of a doubled row)
            # stays with the line before it, so nothing is sung while the screen is blank.
            q_next = runs[off + 1][0] if off + 1 < len(runs) else len(phrases)
            spans = phrases[q:q_next]
            start, end = spans[0][0], spans[-1][1] + 0.25
            if off + 1 < len(runs):
                end = min(end, phrases[runs[off + 1][0]][0] - 0.05)
            placed.append((start, min(max(end, start + 0.6), hi), spans))
        before = sum(_voiced(segs, l["start"], l["end"]) for l in lines[a:b])
        after = sum(_voiced(segs, s0, e0) for s0, e0, _ in placed)
        if after <= before:
            continue
        for off, (start, end, spans) in enumerate(placed):
            l = lines[a + off]
            l["start"], l["end"] = round(start, 2), round(end, 2)
            l["words"] = _time_words_on_phrases(l, spans, time_line_words)
            l["timing_source"] = "voice"
            fixed += 1
    if fixed:
        log.info(f"[Sync Repair] {fixed} lines re-placed onto the sung phrases")
    return fixed


def repair_sync(lines: List[Line], vocal_segments: Optional[List[Tuple[float, float]]]) -> Dict[str, int]:
    """Runs every repair in order; returns how many lines each one changed."""
    from_repeats = repair_from_repeats(lines)
    on_voice = refit_to_voice(lines, vocal_segments)
    at_breaks = end_lines_at_breaks(lines, vocal_segments)
    return {"from_repeats": from_repeats, "refit_to_voice": on_voice, "ended_at_breaks": at_breaks}
