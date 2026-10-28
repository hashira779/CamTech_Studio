"""
Finds rows left out when lyrics were pasted, using the song's own repeats.

A verse or chorus sung twice should be written out twice the same way. If one copy lacks a row,
the two copies stop lining up at exactly that spot: rows before it pair up at one distance and
rows after it at a distance one longer. That shift says where the row is missing and, from the
other copy, which row it is, without any transcript. Nothing is changed here; the studio offers
each missing row for the user to add or ignore.

(Word-level fixes from a transcript were measured and rejected: the acoustic check rewards
spellings that sound closer, so it preferred misspellings such as បតិវាត់ over បដិវត្តន៍, and gave
opposite verdicts for the same line sung twice.)
"""

import re
from typing import Any, Dict, List

# Each side of the break must be a run of identical rows, not a stray echo.
MIN_RUN = 2
MIN_SECTION = 4
# Putting the row back must re-join at least this many matching rows. A gain of 1 is what any
# passage edge gives (an outro after verse 2, say), so it is not evidence of a missing row.
MIN_GAIN = 2


def _key(text: str) -> str:
    t = re.sub("[៍៎៏​‌‍]", "", str(text)).replace("្ដ", "្ត")
    return re.sub(r"[\W_]+", "", t, flags=re.UNICODE).lower()


def _runs(keys: List[str], d: int) -> List[List[int]]:
    """Runs of consecutive i where row i and row i+d are the same lyric."""
    runs: List[List[int]] = []
    for i in range(len(keys) - d):
        if keys[i] and keys[i] == keys[i + d]:
            if runs and runs[-1][1] == i - 1:
                runs[-1][1] = i
            else:
                runs.append([i, i])
    return runs


def find_missing_rows(lines: List[str]) -> List[Dict[str, Any]]:
    """
    Rows one copy of a repeated section has and the other lacks. Each result says to insert
    `text` after row `after` (0-based, -1 for the very start), copied from row `source`.
    """
    keys = [_key(t) for t in lines]
    n = len(keys)
    found: Dict[int, Dict[str, Any]] = {}
    # A repeat can sit just past half the song when its second copy is the one short a row.
    for d in range(1, n - MIN_RUN + 1):
        for s1, e1 in _runs(keys, d):
            if e1 - s1 + 1 < MIN_RUN:
                continue
            # copy B has one row more: pairs resume at distance d+1 right after this run
            for s2, e2 in _runs(keys, d + 1):
                # the runs meet at the gap, or overlap by a row when the gap sits beside an identical row
                if s1 < s2 <= e1 + 1 <= e2 and e2 - s2 + 1 >= MIN_RUN and (e1 - s1 + 1) + (e2 - s2 + 1) >= MIN_SECTION:
                    extra = e1 + d + 1  # the row only copy B has
                    if 0 <= extra < n and keys[extra]:
                        found.setdefault(e1, {"after": e1, "text": lines[extra], "source": extra, "distance": d})
            # copy A has one row more: pairs resume at distance d-1 one row later
            if d > 1:
                for s2, e2 in _runs(keys, d - 1):
                    if s1 < s2 <= e1 + 2 <= e2 and e2 - s2 + 1 >= MIN_RUN and (e1 - s1 + 1) + (e2 - s2 + 1) >= MIN_SECTION:
                        extra = e1 + 1  # the row only copy A has
                        after = e1 + d  # where it belongs in copy B
                        if keys[extra]:
                            found.setdefault(after, {"after": after, "text": lines[extra], "source": extra, "distance": d})
    # A real missing row, once put back, makes the copies line up over a longer stretch.
    # A candidate that does not (e.g. one that lengthens the copy that was already longer) is dropped.
    before = _longest_repeat(keys)
    kept = []
    for k in sorted(found):
        m = found[k]
        trial = keys[:m["after"] + 1] + [keys[m["source"]]] + keys[m["after"] + 1:]
        gain = _longest_repeat(trial) - before
        if gain >= MIN_GAIN:
            kept.append({**m, "gain": gain})
    return kept


def _longest_repeat(keys: List[str]) -> int:
    """Length of the longest run of rows that repeat at one fixed distance."""
    best = 0
    for d in range(1, len(keys)):
        for s, e in _runs(keys, d):
            best = max(best, e - s + 1)
    return best


def missing_row_groups(lines: List[str]) -> List[List[Dict[str, Any]]]:
    """
    find_missing_rows, with mirror images grouped. When a passage repeats inside itself, one
    left-out row can be explained as missing from either copy, and neither the text nor the
    audio can tell which (measured: re-aligning with each option moved the fit by under 0.005).
    Such candidates sit one section apart and are offered together for the user to choose.
    """
    rows = find_missing_rows(lines)
    groups: List[List[Dict[str, Any]]] = []
    for r in rows:
        for g in groups:
            if any(abs(abs(r["after"] - o["after"]) - o["distance"]) <= 1 for o in g):
                g.append(r)
                break
        else:
            groups.append([r])
    # Within one gap, keep the explanation that re-unifies the copies best; a tie stays a choice.
    return [[r for r in g if r["gain"] == max(o["gain"] for o in g)] for g in groups]


def doubled_rows(lines: List[str]) -> List[Dict[str, Any]]:
    """
    Rows that write one phrase twice ("ទៅណាមកណា ទៅណាមកណា"), grouped by phrase. The singer usually
    sings each as its own phrase, so the studio offers to show each on its own line; it is offered,
    not done, because some (a quick "ភ័យណាស់ ភ័យណាស់") would flash by in well under a second.
    Each group gives the 0-based line indexes and the two halves as written.
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for i, text in enumerate(lines):
        parts = text.split()
        half = len(parts) // 2
        if not half or len(parts) % 2 or [_key(p) for p in parts[:half]] != [_key(p) for p in parts[half:]]:
            continue
        first, second = " ".join(parts[:half]), " ".join(parts[half:])
        g = groups.setdefault(_key(first), {"phrase": first, "lines": [], "halves": [first, second]})
        g["lines"].append(i)
    return list(groups.values())


# Singing the lyrics do not contain shows up as a jump inside a barely heard line: the aligner has
# to stretch the line over the unlisted words, so two of its words land seconds apart while the
# voice never stops. Measured on 10 songs: 3 such spots, 2 confirmed by the user as the second
# singer's part of a duet (the same spot in both verses). Clearly heard lines are skipped: a jump
# there is a long held note.
UNLISTED_MAX_CONF = 0.3
UNLISTED_MIN_JUMP_S = 3.0
UNLISTED_MIN_VOICED = 0.9


def unlisted_singing(lines: List[Dict[str, Any]], vocal_segments) -> List[Dict[str, Any]]:
    """Stretches where someone sings words the lyrics do not contain, with the line they fall in."""
    segs = sorted((float(s), float(e)) for s, e in (vocal_segments or []))
    if not segs:
        return []

    def voiced(a: float, b: float) -> float:
        return sum(max(0.0, min(e, b) - max(s, a)) for s, e in segs) / (b - a) if b > a else 0.0

    found = []
    for i, line in enumerate(lines):
        if float(line.get("confidence", 1.0)) >= UNLISTED_MAX_CONF:
            continue
        words = line.get("words") or []
        for a, b in zip(words, words[1:]):
            start, end = float(a["start"]) + 0.5, float(b["start"])
            if end - float(a["start"]) >= UNLISTED_MIN_JUMP_S and voiced(start, end) >= UNLISTED_MIN_VOICED:
                found.append({"line": i, "start": round(start, 2), "end": round(end, 2),
                              "after_word": a.get("word", ""), "before_word": b.get("word", "")})
                break
    return found
