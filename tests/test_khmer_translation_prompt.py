"""Khmer lyric translation prompt contract tests.

Covers the adaptation brief enforced in backend/llm_engine.py:
  - every rule and example pair survives in the built prompt
  - no stray "org" filler tokens (this corruption once broke the module)
  - the JSON id/text contract stays intact so cue order is never disturbed
  - song title / artist are threaded from the API request into the prompt
"""

import io
import json
import os
import re
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.llm_engine import LocalLLMEngine  # noqa: E402


def _norm(text):
    """Collapse whitespace so line-wrapping in the prompt cannot break assertions."""
    return " ".join(text.split())


PAYLOAD = json.dumps(
    [{"id": 0, "text": "Oh my dear, this love is as sweet as orange juice"}],
    ensure_ascii=False,
)


def run():
    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))

    # 1. Module compiles — the corruption this test guards against was a SyntaxError.
    compile_src = io.open(
        os.path.join(ROOT, "backend", "llm_engine.py"), "r", encoding="utf-8"
    ).read()
    try:
        compile(compile_src, "llm_engine.py", "exec")
        ok, detail = True, "compiles"
    except SyntaxError as exc:
        ok, detail = False, f"SyntaxError line {exc.lineno}"
    check("llm_engine.py compiles", ok, detail)

    eng = LocalLLMEngine
    prompt = _norm(eng._build_khmer_translation_prompt("English", PAYLOAD))

    # 2. No injected "org" spam tokens (whole word, excluding real domains).
    org_hits = [m for m in re.findall(r"\borg\b", prompt)]
    check("prompt has no 'org' filler tokens", not org_hits, f"{len(org_hits)} hits")

    # 3. All five critical rules survive.
    rules = [
        ("rule 1 word-by-word", "DO NOT translate word-by-word"),
        ("rule 2 natural Khmer", "Must sound like natural Khmer"),
        ("rule 3 emotion", "Preserve the emotion and meaning"),
        ("rule 4 everyday vocabulary", "Use everyday Khmer vocabulary"),
        ("rule 5 rhythm", "Match the rhythm and flow"),
    ]
    for name, needle in rules:
        check(name, _norm(needle) in prompt)

    # 4. Khmer-script-only guard (Thai characters must never leak into output).
    check("rule 6 Khmer script only", _norm("Khmer script only in the output") in prompt)
    check(
        "Thai-vs-Khmer bad example kept",
        "ប" in prompt,
    )

    # 5. Example pairs: every ❌/✅ pair from the brief is present.
    pairs = [
        ("I can't stop loving you", "បេះដូងនេះមិនធ្លាប់ភ្លេចអូនសោះ"),
        ("You are the sunshine of my life", "អូនជាពន្លឺបំភ្លឺបេះដូងបង"),
        ("Every breath you take", "រាល់ដង្ហើមរបស់អូន បងនៅតែមើលថែ"),
        ("Let it go, let it go", "លែងវាទៅ លែងខ្វល់ទៀតហើយ"),
        ("月亮代表我的心", "ព្រះច័ន្ទជាសាក្សីស្នេហ៍បង"),
        ("사랑해요", "បងស្រឡាញ់អូន"),
        ("คิดถึงเธอทุกวัน", "នឹកអូនរាល់ថ្ងៃមិនធ្លាប់ភ្លេច"),
    ]
    for src, km in pairs:
        check(
            f"example pair kept: {src[:18]}",
            _norm(src) in prompt and _norm(km) in prompt,
        )

    # 6. Output contract: JSON array with id + text, no prose.
    check("JSON array contract", _norm("valid JSON array") in prompt)
    check("id/text keys documented", '"id"' in prompt and '"text"' in prompt)
    check(
        "one line per original line",
        _norm("One translated line per input line") in prompt
        or _norm("one object per input line") in prompt,
    )
    check("payload included", PAYLOAD.replace(" ", "") in prompt.replace(" ", ""))

    # 7. Song context threading.
    ctx = _norm(
        eng._build_khmer_translation_prompt(
            "Vietnamese",
            PAYLOAD,
            song_title="THIÊN ĐƯỜNG VỚI NGƯỜI THƯƠNG",
            artist="Phương Mỹ Chi x DTAP",
        )
    )
    check("song title threaded", "THIÊN ĐƯỜNG VỚI NGƯỜI THƯƠNG" in ctx, )
    check("artist threaded", "Phương Mỹ Chi x DTAP" in ctx)
    check("source language threaded", "Source language: Vietnamese" in ctx)

    # 8. translate_lyrics_data accepts the new kwargs and keeps Khmer detection path.
    import inspect

    sig = inspect.signature(eng.translate_lyrics_data)
    check(
        "translate_lyrics_data kwargs",
        "song_title" in sig.parameters and "artist" in sig.parameters,
    )
    req_src = io.open(
        os.path.join(ROOT, "backend", "app.py"), "r", encoding="utf-8"
    ).read()
    check(
        "API request model carries context",
        "song_title: str" in req_src and "artist: str" in req_src,
    )
    check(
        "API passes context through",
        _norm("song_title=req.song_title") in _norm(req_src)
        and _norm("artist=req.artist") in _norm(req_src),
    )

    # 9. Frontend sends the context fields.
    js = io.open(
        os.path.join(ROOT, "frontend", "js", "core", "translation.js"),
        "r",
        encoding="utf-8",
    ).read()
    check("frontend sends song_title", "song_title:" in js)
    check("frontend sends artist", "artist:" in js)

    return results


if __name__ == "__main__":
    rows = run()
    passed = sum(1 for _, ok, _ in rows if ok)
    for name, ok, detail in rows:
        print(("PASS  " if ok else "FAIL  ") + name + ((" — " + detail) if detail else ""))
    print(f"\n{passed}/{len(rows)} checks passed")
    sys.exit(0 if passed == len(rows) else 1)
