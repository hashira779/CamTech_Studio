"""
Guards the Khmer spelling handed to the word aligner (backend/ctc_align._khmer_as_sung):
sounds the singer never makes are removed, sounds the singer does make are kept.
Run: python tests/test_khmer_romanize.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.ctc_align import _get_uroman, _khmer_as_sung

PASS, FAIL = [], []


def check(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(("  ok   " if cond else "  FAIL ") + msg)


def run():
    ur = _get_uroman()
    sung = lambda w: _khmer_as_sung(ur.romanize_string(w, lcode="khm"))

    print("closed syllables lose the vowel uroman adds after the final consonant")
    for word, expect in [("បង", "bang"), ("ព្រម", "prom"), ("យក", "yok"), ("មិន", "min"), ("ភ័យ", "phoy")]:
        check(sung(word) == expect, f"{word} -> {sung(word)!r} (expected {expect!r})")

    print("silent អ onset and doubled ណ")
    check(sung("អូន") == "uun", f"អូន -> {sung('អូន')!r} drops the q for the silent onset")
    check(sung("ណាស់") == "naas", f"ណាស់ -> {sung('ណាស់')!r} uses a single n and no trailing vowel")

    print("open syllables keep their vowel")
    for word, expect in [("ណា", "naa"), ("ទេ", "te"), ("ជា", "caa"), ("ទៅ", "tau")]:
        check(sung(word) == expect, f"{word} -> {sung(word)!r} (expected {expect!r})")

    check(_khmer_as_sung("ok") == "ok", "very short spellings are left alone")

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed\n")
    for m in FAIL:
        print("FAILED: " + m)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(run())
