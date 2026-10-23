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

    # --- meaning-first brief ---------------------------------------------------
    # The complaint this guards against is literal Khmer that natives cannot listen to,
    # so the prompt has to carry a procedure, a singability budget and a consistent voice.
    procedure = [
        ("MEANING FIRST heading", "MEANING FIRST, NEVER LETTER FOR LETTER"),
        ("step 1 grasp the meaning", "GRASP THE MEANING"),
        ("step 2 drop the source sentence", "DROP THE SOURCE SENTENCE"),
        ("step 3 say it in Khmer", "SAY IT IN KHMER"),
        ("step 4 back-check aloud", "BACK-CHECK ALOUD"),
        ("rule 7 consistent voice", "Pick one voice and keep it"),
        ("rule 8 one line in one line out", "One line in, one line out"),
        ("singability budget", "24 sung units"),
        ("no transliteration", "Never romanise or transliterate a source word"),
        ("idea not letters", "translate the IDEA of each line"),
        ("examples teach style only", "teach the STYLE, not the answer"),
        ("no recycling examples", "you have recycled it"),
    ]
    for name, needle in procedure:
        check(name, _norm(needle) in prompt)
    check(
        "source language used inside the procedure",
        "forget the English word order" in prompt,
        prompt[prompt.find("STEP 2"):prompt.find("STEP 2") + 60] if "STEP 2" in prompt else "STEP 2 missing",
    )

    extra_pairs = [
        ("this love is as sweet as orange juice", "ស្នេហ៍យើងផ្អែមល្អណាស់"),
        ("Yêu em thầm lặng", "បងស្រឡាញ់អូនមិនហ៊ានប្រាប់"),
    ]
    for src, km in extra_pairs:
        check(f"added pair: {src[:22]}", _norm(src) in prompt and _norm(km) in prompt)

    # --- shared rewrite brief --------------------------------------------------
    polish = _norm(
        eng._build_khmer_polish_prompt(
            "Vietnamese", '[{"id": 0, "original": "abc", "khmer": "xyz", "issue": "unchanged"}]'
        )
    )
    check("polish brief exists", "Khmer song lyricist" in polish)
    check("polish brief keeps meaning of the original", "carries the MEANING" in polish)
    check("polish brief reads the reported issue", "'issue' says what the studio" in polish and "fix exactly that" in polish)
    check("polish brief demands natural native Khmer", "បកប្រែតាមអត្ថន័យ មិនតាមអក្សរ" in polish)
    check("polish brief has a singability budget", "24 " in polish and "sung units" in polish)
    check("polish brief forbids foreign letters", "Khmer script only" in polish)
    check("polish brief keeps 1:1 integrity", "STRICT 1:1 LINE INTEGRITY" in polish)
    check("polish brief outputs id/text JSON", '[{"id": 0, "text": "..."}]' in polish)
    check("polish brief carries song context", "THIÊN ĐƯỜNG" not in polish)  # not passed -> 'not provided'
    check(
        "polish brief names the artist when given",
        "DTAP"
        in _norm(
            eng._build_khmer_polish_prompt("Vietnamese", "[]", song_title="T", artist="Phương Mỹ Chi x DTAP")
        ),
    )

    # --- the deterministic ear test -------------------------------------------
    inst = LocalLLMEngine()
    # Sung units follow the timing engine's convention: a coeng (subscript) consonant does not
    # add a unit, a final consonant does. ប្រណាំង is ប-រ-ណ-ង written but ប-ណ-ង sung.
    check("coeng does not add a sung unit", inst._sung_syllables("ប្រណាំង") == 3,
          str(inst._sung_syllables("ប្រណាំង")))
    check("final consonant counts as a unit", inst._sung_syllables("បង") == 2,
          str(inst._sung_syllables("បង")))
    check("clustered word sings as one line", inst._sung_syllables("ស្នេហ៍") == 2,
          str(inst._sung_syllables("ស្នេហ៍")))
    check("latin vowel groups counted",
          inst._sung_syllables("Yêu em thầm lặng") >= 3, str(inst._sung_syllables("Yêu em thầm lặng")))
    check("empty line is zero", inst._sung_syllables("") == 0)
    # The cap comes from the studio's own Khmer corpus: median 17, p97 22, longest 25 sung units.
    check("corpus-calibrated line cap", inst.KHMER_LINE_UNIT_CAP == 24,
          str(inst.KHMER_LINE_UNIT_CAP))
    check("rewrite timeout is a measured budget", eng.KHMER_DRAFT_TIMEOUT_S >= 120,
          str(eng.KHMER_DRAFT_TIMEOUT_S))
    check("rewrite timeout covers the real 44s call", eng.KHMER_POLISH_TIMEOUT_S >= 120,
          str(eng.KHMER_POLISH_TIMEOUT_S))

    # --- tolerant reply parsing -------------------------------------------------
    # The Khmer requests are the most expensive button presses in the studio, and a reply shaped
    # {"translations": [...]} or wrapped in a ```json fence used to raise inside json.loads and
    # lose the whole translation. Those shapes are read now.
    reply_cases = [
        ("plain array", '[{"id": 0, "text": "បងស្រឡាញ់អូន"}]', {"0": "បងស្រឡាញ់អូន"}),
        ("fenced array", '```json\n[{"id": 1, "text": "អូនជាពន្លឺ"}]\n```', {"1": "អូនជាពន្លឺ"}),
        ("prose before the array", 'Sure! [{"id": 2, "text": "លែងវាទៅ"}]', {"2": "លែងវាទៅ"}),
        ("object wrapper", '{"translations": [{"id": 3, "text": "នឹកអូន"}]}', {"3": "នឹកអូន"}),
        ("alternate text key", '[{"id": 4, "translation": "ខ្លែងហោះ"}]', {"4": "ខ្លែងហោះ"}),
        ("empty text is dropped", '[{"id": 5, "text": "   "}]', {}),
        ("unreadable reply", 'not json at all', {}),
        ("no items", '[]', {}),
    ]
    for name, raw, expected in reply_cases:
        got = inst._parse_id_text(raw)
        check(f"reply parses: {name}", got == expected, str(got))

    check("reply ids are normalised", inst._parse_id_text('[{"id": 7, "text": "អូន"}]') == {"7": "អូន"})
    check(
        "require_id refuses an id-less line",
        inst._parse_id_text('[{"text": "អូន"}]', require_id=True) == {},
    )
    check(
        "without require_id an id-less line keeps its position",
        inst._parse_id_text('[{"text": "អូន"}]') == {"0": "អូន"},
    )

    # A rewrite pass must never guess which line an id-less answer belongs to.
    polish_src = _norm(io.open(os.path.join(ROOT, "backend", "llm_engine.py"), "r", encoding="utf-8").read())
    check("the rewrite pass demands explicit ids", "require_id=True" in polish_src)
    check(
        "a failed grading pass keeps the draft",
        "grading pass failed, keeping the ungraded draft" in polish_src,
    )
    check(
        "an unusable draft reply is retried, not returned",
        "not usable id/text JSON, retrying once" in polish_src,
    )
    check(
        "a dead Gemini call is logged, not silent",
        "no model answered this request" in polish_src,
    )
    api_src = _norm(io.open(os.path.join(ROOT, "backend", "app.py"), "r", encoding="utf-8").read())
    check(
        "the studio says why nothing changed",
        "Gemini answered but repeated the original lines" in api_src and "get_last_key_error" in api_src,
    )
    check("a spent quota is reported as a spent quota", "Gemini is rate-limiting this key" in api_src)
    check("the rewrite pass tells the UI why it did nothing", '"service_notice"' in api_src)
    check("the studio repeats that reason in its own toast",
          "service_notice" in js and "serviceNotice" in js
          and "no line could be rewritten" in js)

    # Simplified to 3 models: latest (auto-routes to newest), a pinned stable version,
    # and a lite fallback in a separate rate bucket. Fewer models = faster failover.
    llm_raw = io.open(os.path.join(ROOT, "backend", "llm_engine.py"), "r", encoding="utf-8").read()
    fm = re.search(r"models\s*=\s*\[(.*?)\]", llm_raw, re.S)
    fallback_list = re.findall(r'"([^"]+)"', fm.group(1)) if fm else []
    dead_names = {"gemini-3.1-flash", "gemini-3-flash", "gemini-2.0-flash"}
    check("the fallback list was read from the source", len(fallback_list) >= 3, str(fallback_list))
    check("dead 404 model names are gone",
          not (dead_names & set(fallback_list)), str(sorted(dead_names & set(fallback_list))))
    check("fallback keeps the models that do answer",
          "gemini-3.8-flash" in fallback_list and "gemini-flash-latest" in fallback_list,
          str(fallback_list))
    check("the reply parser is what the rewrite pass uses", "self._parse_id_text(res_str)" in polish_src)

    ear_cases = [
        ("empty draft is flagged", "", ["empty"]),
        ("untranslated source is flagged", "Yêu em thầm lặng", ["no_khmer", "foreign_letters", "unchanged"]),
        ("Thai letters leaking in are flagged", "ปล่อយវាទៅ", ["foreign_letters"]),
        ("romantic natural line passes", "បងស្រឡាញ់អូនមិនហ៊ានប្រាប់", []),
        ("absurdly long line is un-singable", "ប" * 25, ["too_long_to_sing"]),
    ]
    for name, draft, expected in ear_cases:
        got = inst._khmer_line_issues("Yêu em thầm lặng", draft)
        if expected == []:
            check(name, got == [], str(got))
        else:
            check(name, all(e in got for e in expected), str(got))

    # Real native lines from the studio corpus must never be shouted down by the length guard.
    for real_km in [
        "ចង់ប្រាប់អូនថាបងស្រឡាញ់អូន",
        "រាល់ដង្ហើមរបស់អូន បងនៅតែមើលថែ",
        "អ្នកណាដែលមិនធ្លាប់ស្រឡាញ់ អ្នកណាដែលមិនធ្លាប់វង្វេង",
    ]:
        check(
            f"real Khmer line passes the length guard: {real_km[:16]}",
            "too_long_to_sing" not in inst._khmer_line_issues("Một câu yêu thương muốn nói", real_km),
            f"units={inst._sung_syllables(real_km)}",
        )

    # The ear test has to catch the calques themselves, not only broken script.
    ear_grade_cases = [
        ("sunshine-of-my-life calque caught", "You are the sunshine of my life",
         "អ្នកជាពន្លឺថ្ងៃនៃជីវិតរបស់ខ្ញុំ", ["stiff_possessive_chain"]),
        ("can't-stop-loving calque caught", "I can't stop loving you",
         "ខ្ញុំមិនអាចបញ្ឈប់ការស្រឡាញ់អ្នក", ["literal_calque"]),
        ("moon-represents calque caught", "月亮代表我的心",
         "ព្រះច័ន្ទតំណាងបេះដូងរបស់ខ្ញុំ", ["literal_calque"]),
        ("natural possessive once is fine", "You are my heart", "អូនជាដួងចិត្តរបស់បង", []),
        ("natural idiom passes", "Let it go", "លែងវាទៅ លែងខ្វល់ទៀតហើយ", []),
        ("natural longing passes", "Nhớ em mỗi ngày", "នឹកអូនរាល់ថ្ងៃមិនធ្លាប់ភ្លេច", []),
    ]
    for name, src, draft, expected in ear_grade_cases:
        got = inst._khmer_line_issues(src, draft)
        ok = (got == []) if expected == [] else all(e in got for e in expected)
        check(name, ok, str(got))

    # Lines taken from the studio's own Khmer corpus must pass the guards untouched — the flags
    # are calibrated on native lyrics (median 17 sung units, p97 22), not on a theory.
    for native in [
        "ទោះនៅបាតអណ្ដូងក៏ជាឋានសួគ៌ឱ្យតែបាននៅក្បែរអូន",
        "អូនជាពន្លឺបំភ្លឺបេះដូងបង",
        "បេះដូងនេះមិនធ្លាប់ភ្លេចអូនសោះ",
        "អើយមនុស្សអើយ",
    ]:
        check(f"native corpus line passes: {native[:14]}",
              inst._khmer_line_issues("Một câu hát", native) == [],
              str(inst._khmer_line_issues("Một câu hát", native)))
    check(
        "the over-long literal corpus line is caught",
        "too_long_to_sing" in inst._khmer_line_issues(
            "Chèo thuyền rồi ăn cơm chung", "ប្រណាំងទូកហើយញ៉ាំបាយជាមួយគ្នា អយស្ទ័រនិងទឹកអម្ពិល"
        ),
        f"units={inst._sung_syllables('ប្រណាំងទូកហើយញ៉ាំបាយជាមួយគ្នា អយស្ទ័រនិងទឹកអម្ពិល')}",
    )

    # --- wiring ---------------------------------------------------------------
    import inspect

    sig = inspect.signature(eng.translate_lyrics_data)
    check("auto_polish knob exists", "auto_polish" in sig.parameters)
    src = io.open(
        os.path.join(ROOT, "backend", "llm_engine.py"), "r", encoding="utf-8"
    ).read()
    check("translation grades Khmer output", "_grade_and_polish_khmer(" in src)
    check("grading rewrites only flagged lines", "flagged.append(" in src)
    check("rewrite cannot make a line worse", "the rewrite did not help" in src)
    check("refine shares the one rewrite brief", "self._polish_khmer_pairs(" in src)
    check("naturalness is reported per line", '"naturalness"' in src)
    check("grader carries a calque list", "_KHMER_CALQUES" in src)
    check("Gemini fallback gets an overall deadline",
          "total_timeout=self.KHMER_DRAFT_TIMEOUT_S" in src
          and "total_timeout=self.KHMER_POLISH_TIMEOUT_S" in src
          and "left = total_timeout" in src)
    check("an echoed translation is retried once", "retrying once" in src)
    check(
        "API exposes the counts",
        "khmer_natural" in req_src and "khmer_literal" in req_src,
    )
    check("API forwards auto_polish", _norm("auto_polish=req.polish") in _norm(req_src))
    check("request model has the polish knob", "polish: bool" in req_src)
    check("frontend asks for the polish pass", "polish: true" in js)
    check("frontend reads the naturalness report", "khmerNaturalnessNote" in js)
    check("frontend warns about literal lines", "still sound translated" in js)
    check("editor progress names the polish stage", "'Polishing Khmer'" in js)
    # Khmer now ships in smaller batches with a budget that survives draft + rewrite + retry.
    check("khmer batches are 12 lines", "BATCH_SIZE = isKhmer ? 12 : 25" in js)
    check("khmer request budget covers the retry", "isKhmer ? 600000 : 180000" in js)
    check("editor marks the lines still flagged", "te-input--literal" in js)
    check("the editor seeds its flags straight from the returned grades",
          "getKhmerLiteralRows()" in js and "collectKhmerLiteralRows" in js)
    check("a model that did answer clears the rate-limit note",
          llm_raw.count("LAST_GEMINI_STATUS = None") >= 2,
          str(llm_raw.count("LAST_GEMINI_STATUS = None")))
    css = io.open(os.path.join(ROOT, "frontend", "css", "style.css"), "r", encoding="utf-8").read()
    check("the flag has a style", ".te-input--literal" in css)

    return results


if __name__ == "__main__":
    rows = run()
    passed = sum(1 for _, ok, _ in rows if ok)
    for name, ok, detail in rows:
        print(("PASS  " if ok else "FAIL  ") + name + ((" — " + detail) if detail else ""))
    print(f"\n{passed}/{len(rows)} checks passed")
    sys.exit(0 if passed == len(rows) else 1)
