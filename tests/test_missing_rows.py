"""
Guards the paste check for rows left out of pasted lyrics (backend/services/lyric_review.py):

  - a complete paste raises nothing
  - a row dropped from either copy of a repeated passage is found, at the right place, with
    the right text copied from the other copy
  - where the text cannot tell which copy lost the row, both options are offered together
    and the true one is among them
  - the insert position maps back to the pasted row, past "ភ្លេង" and blank lines
Run: python tests/test_missing_rows.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.lyric_alignment import parse_reference_rows
from backend.services.lyric_review import doubled_rows, missing_row_groups, unlisted_singing

PASS, FAIL = [], []


def check(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg)


# The verse of សុភាពបុរសចេះដាល់ (Sinn Sisamouth), sung twice with an instrumental between.
VERSE = """ចិត្តបងជាសុភាពបុរស
នែស្រឡាញ់បងចុះ ថាមិនខុសទេស្រី
ព្រមទៅយកបងធ្វើប្ដី
អូនអើយ កុំភ័យបងការពារ
ព្រមទៅយកបងធ្វើប្ដី
អូនអើយ កុំភ័យបងការពារ
ទៅណាមកណា ទៅណាមកណា
អ្នកណាក៏មិនហ៊ាននឹងបងដែរ
អ្នកប្រដាល់ស្រុកខ្មែរគេខ្លាចតែបងទេ
ចិត្តបងជាសុភាពបុរស
នែបងចេះទាំងអស់ស្នៀតប្រដាល់សេរី
បងឈ្នះគ្រប់ទិសប្រាំបី
អ្នកប្រដាល់ជើងថ្មី ភ័យនឹងបងណាស់
បងឈ្នះគ្រប់ទិសប្រាំបី
អ្នកប្រដាល់ជើងថ្មី ភ័យនឹងបងណាស់
ភ័យណាស់ ភ័យណាស់
មិនហ៊ានមកប៉ះនឹងបងទេ
ល្បីពេញស្រុកខ្មែររហូតទៅដល់ស្រុកថៃ""".split("\n")
SONG = VERSE + VERSE


def groups_for(lines):
    return [[(o["after"], o["text"]) for o in g] for g in missing_row_groups(lines)]


def run():
    print("complete lyrics")
    check(groups_for(SONG) == [], "a complete paste raises nothing")
    check(groups_for(VERSE) == [], "a song with no repeats raises nothing")

    print("a row dropped from one copy")
    dropped = SONG[:5] + SONG[6:]  # verse 1 loses "អូនអើយ កុំភ័យបងការពារ" (row 6)
    check(groups_for(dropped) == [[(4, SONG[5])]],
          "found after row 5 with the exact row from the other verse, as a single clear option")

    n = len(VERSE)
    dropped = SONG[:n + 7] + SONG[n + 8:]  # verse 2 loses "អ្នកណាក៏មិនហ៊ាននឹងបងដែរ"
    found = groups_for(dropped)
    check(len(found) == 1 and (n + 6, SONG[7]) in found[0], "a row dropped from the second copy is found too")

    print("a spot inside a passage that repeats itself")
    dropped = SONG[:11] + SONG[12:]  # verse 1 loses "បងឈ្នះគ្រប់ទិសប្រាំបី" (row 12)
    found = groups_for(dropped)
    check(found == [[(10, SONG[11])]],
          "the explanation that re-joins the verses best wins, and it is the true row")

    print("a row next to an identical row")
    song = VERSE[:15] + [VERSE[15]] + VERSE[15:] + VERSE[:15] + [VERSE[15]] + VERSE[15:]
    dropped = song[:15] + song[16:]  # one of the two "ភ័យណាស់ ភ័យណាស់" rows
    found = groups_for(dropped)
    fixes = [dropped[:a + 1] + [t] + dropped[a + 1:] for g in found for a, t in g]
    check(song in fixes, "found, and adding it back restores the lyrics")

    print("passage edges are not evidence")
    outro = SONG + SONG[-2:]  # an outro repeating the last two rows
    check(groups_for(outro) == [], "a song whose second copy ends with an outro raises nothing")

    print("rows that write one phrase twice")
    found = doubled_rows(SONG)
    phrases = {d["phrase"]: [i + 1 for i in d["lines"]] for d in found}
    check(phrases == {"ទៅណាមកណា": [7, 25], "ភ័យណាស់": [16, 34]},
          "each doubled phrase is found once, with every row that has it")
    check(all(d["halves"][0] == d["halves"][1] for d in found), "each row splits into two equal halves")
    check(doubled_rows(["ដៃក៏រឹងជើងក៏រឹង", "ចិត្តបងជាសុភាពបុរស"]) == [], "ordinary rows are not offered")

    print("labels in square brackets")
    tagged = "[Verse 1]\n[Singer 1]\nWalking down (lonely road)\n[Chorus]\n[Both / Duet] Don't look back\n[Pre-Chorus]"
    lines = [t for _, t in parse_reference_rows(tagged)]
    check(lines == ["Walking down (lonely road)", "Don't look back"],
          "section and singer labels are dropped, lyrics and backing vocals in ( ) are kept")

    print("singing that is not in the lyrics")
    w = lambda word, t: {"word": word, "start": t, "end": t + 0.4}
    stretched = {"confidence": 0.12, "words": [w("កុំ", 26.3), w("ខឹង", 26.9), w("ប្រុស", 33.1), w("ព្រលឹង", 33.7)]}
    held = {"confidence": 0.64, "words": [w("ឱ", 70.2), w("អើយ", 76.4)]}
    normal = {"confidence": 0.1, "words": [w("ទើប", 22.1), w("ជួបគ្នា", 22.3), w("ម្ដង", 23.1)]}
    voice = [(18.0, 45.0), (68.0, 80.0)]
    spots = unlisted_singing([normal, stretched, held], voice)
    check(len(spots) == 1 and spots[0]["line"] == 1 and spots[0]["start"] == 27.4 and spots[0]["end"] == 33.1,
          "a barely heard line stretched over continuous singing is reported, with where it happens")
    check(not unlisted_singing([held], voice), "a clearly heard line with a long held note is not reported")
    check(not unlisted_singing([stretched], [(18.0, 28.0), (32.5, 45.0)]),
          "a jump over a pause in the singing is not reported")

    print("mapping back to the pasted text")
    pasted = "\n".join(VERSE[:5] + ["", "ភ្លេង", ""] + VERSE[6:] + VERSE)
    rows = parse_reference_rows(pasted)
    lines = [t for _, t in rows]
    check("ភ្លេង" not in lines and "" not in lines, "instrumental and blank rows are not lyrics")
    g = missing_row_groups(lines)
    check(len(g) == 1 and rows[g[0][0]["after"]][0] == 4,
          "the insert point is the pasted row of line 5, not shifted by the skipped rows")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed\n")
    for m in FAIL:
        print("FAILED: " + m)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(run())
