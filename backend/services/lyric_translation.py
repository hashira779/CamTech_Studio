"""
Khmer song lyrics -> English subtitle lines that keep the meaning.

  1. Lines the user already has in English (any song's saved English track, paired to its Khmer
     line by time) are reused exactly: same Khmer line, same approved English.
  2. The rest are translated by Gemini with the whole song as context and Khmer-specific rules
     (who បង / អូន / ម៉ែ / កូន are, particles, names), never adding or dropping meaning.
  3. A second Gemini pass checks every new line against its Khmer and corrects the ones whose
     meaning drifted.
  4. A Khmer line that repeats gets the same English everywhere.
"""
import glob
import json
import logging
import os
import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads", "audio")
# A translated cue belongs to the Khmer line starting within this of it (the tracks share timing).
PAIR_S = 0.75

_memory_cache: Tuple[Optional[tuple], Dict[str, str]] = (None, {})


def _norm(text: str) -> str:
    return re.sub(r"[\s\W_\d]+", "", text or "")


def is_mostly_khmer(lines: List[str]) -> bool:
    text = "".join(lines)
    km = sum(1 for c in text if "ក" <= c <= "៿")
    letters = sum(1 for c in text if c.isalpha())
    return letters > 0 and km / letters >= 0.6


def translation_memory() -> Dict[str, str]:
    """Khmer line (normalised) -> the English the user's saved tracks give it (most common wins)."""
    global _memory_cache
    from backend.lyric_engine import find_matching_subtitles, parse_subtitle_file
    files = sorted(glob.glob(os.path.join(AUDIO_DIR, "*.en-tr.srt")))
    stamp = tuple((f, os.path.getmtime(f)) for f in files)
    if _memory_cache[0] == stamp:
        return _memory_cache[1]
    seen: Dict[str, Counter] = defaultdict(Counter)
    for en_path in files:
        base = en_path[:-len(".en-tr.srt")]
        audio = next((base + ext for ext in (".mp3", ".wav", ".m4a", ".flac") if os.path.exists(base + ext)), base + ".mp3")
        try:
            src_path = find_matching_subtitles(audio)
            if not src_path:
                continue
            src = parse_subtitle_file(src_path)
            en = parse_subtitle_file(en_path)
        except Exception:
            continue
        for cue in en:
            text = str(cue.get("text", "")).strip()
            if not text:
                continue
            best = min(src, key=lambda l: abs(float(l["start"]) - float(cue["start"])), default=None)
            if best and abs(float(best["start"]) - float(cue["start"])) <= PAIR_S and is_mostly_khmer([best.get("text", "")]):
                seen[_norm(best["text"])][text] += 1
    memory = {k: c.most_common(1)[0][0] for k, c in seen.items() if k}
    _memory_cache = (stamp, memory)
    return memory


RULES = """Rules:
- Translate the meaning of each line, not word for word. Never add an image, feeling or fact that is not in the Khmer, and never leave one out.
- Read the whole song first: work out who sings each line and to whom, and keep that consistent.
- បង is the man (I/me when he sings; you, dear or darling when she sings to him). អូន is the woman (I/me when she sings; you, dear or darling when he sings to her). ម៉ែ is mother. កូន is child, daughter or son, from the context.
- អើយ, ណា, ហើយ, ណាស់, អឺយ, អើ and similar are tone and calling words: "oh" at most, or leave them out.
- Keep place and person names as names in Latin letters (ប៉ៃលិន -> Pailin).
- Plain, natural English a viewer can read in about two seconds: short lines, no rhymes forced in.
- One English line per Khmer line, the same id. No notes, no quotes around lines."""


def _ask(prompt: str) -> Dict[str, str]:
    from backend.llm_engine import call_gemini_api, LocalLLMEngine
    for _ in range(2):
        try:
            reply = call_gemini_api(prompt, json_mode=True, timeout=60, total_timeout=150)
        except Exception as e:
            log.warning(f"[Lyric Translation] Gemini request failed: {e}")
            continue
        parsed = LocalLLMEngine._parse_id_text(reply or "", require_id=True)
        if parsed:
            return parsed
    return {}


def translate_khmer_to_english(lines: List[str], title: str = "", artist: str = "") -> Tuple[List[str], Dict[str, int]]:
    """English line per Khmer line ('' where it could not be translated) and what each step did."""
    memory = translation_memory()
    out = [memory.get(_norm(t), "") for t in lines]
    stats = {"reused": sum(1 for x in out if x), "translated": 0, "corrected": 0}
    todo = [i for i, x in enumerate(out) if not x and lines[i].strip()]
    # One translation per distinct Khmer line, so repeats come out identical.
    first_of: Dict[str, int] = {}
    for i in todo:
        first_of.setdefault(_norm(lines[i]), i)
    ask_ids = sorted(set(first_of.values()))
    song = json.dumps([{"id": i, "text": t} for i, t in enumerate(lines)], ensure_ascii=False)
    fixed = json.dumps([{"id": i, "text": out[i]} for i in range(len(lines)) if out[i]], ensure_ascii=False)
    who = f'Song: "{title or "untitled"}"' + (f" by {artist}" if artist else "")

    if ask_ids:
        prompt = (f"You translate Cambodian (Khmer) song lyrics into English subtitles for a lyric video. {who}.\n"
                  f"{RULES}\n\n"
                  f"The whole song, for context:\n{song}\n\n"
                  f"Lines the user has already translated (keep their voice; do not return them):\n{fixed}\n\n"
                  f"Translate only these ids: {json.dumps(ask_ids)}\n"
                  'Return only a JSON array: [{"id": <id>, "text": "<English>"}].')
        got = _ask(prompt)
        for i in ask_ids:
            text = str(got.get(str(i), "")).strip()
            if text and _norm(text) != _norm(lines[i]):
                out[i] = text
                stats["translated"] += 1

        # Second pass: meaning check of the new lines against the Khmer.
        new_ids = [i for i in ask_ids if out[i]]
        if new_ids:
            pairs = json.dumps([{"id": i, "khmer": lines[i], "english": out[i]} for i in new_ids], ensure_ascii=False)
            review = (f"You check English subtitles of a Cambodian (Khmer) song for meaning. {who}.\n"
                      f"{RULES}\n\n"
                      f"The whole song, for context:\n{song}\n\n"
                      "For each pair below, compare the English with the Khmer. If the English changes, adds or loses "
                      "meaning, or gets who is speaking to whom wrong, write the corrected line. Otherwise return the "
                      f"English exactly as it is.\n{pairs}\n"
                      'Return only a JSON array with every id: [{"id": <id>, "text": "<English>"}].')
            checked = _ask(review)
            for i in new_ids:
                text = str(checked.get(str(i), "")).strip()
                if text and _norm(text) != _norm(lines[i]) and text != out[i]:
                    out[i] = text
                    stats["corrected"] += 1

    for i in todo:
        out[i] = out[i] or out[first_of[_norm(lines[i])]]
    log.info(f"[Lyric Translation] {len(lines)} Khmer lines -> English: {stats['reused']} reused from your tracks, "
             f"{stats['translated']} translated, {stats['corrected']} corrected for meaning")
    return out, stats
