"""
Stage 3.5 — Khmer Text Post-Processing & Normalization
======================================================
Post-processes raw Whisper transcriptions to:
1. Normalize Khmer Unicode and zero-width spaces
2. Fix known Whisper Khmer singing spelling errors & character confusions
3. Suppress repetitive hallucination loops (e.g. repeating phrases in silence/music)
4. Perform word segmentation normalization using khmer-nltk (CRF-based)
"""

import re
import logging
from typing import List, Dict, Any, Optional

log = logging.getLogger(__name__)

# Try loading khmer-nltk (safe fallback if missing)
try:
    import khmernltk
    _KHMER_NLTK_AVAILABLE = True
except ImportError:
    khmernltk = None
    _KHMER_NLTK_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Common Whisper Khmer singing misrecognitions & spelling standardizations
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_KHMER_FIXES: Dict[str, str] = {
    "បេស្ដូង": "បេះដូង",    # heart
    "បេះដង": "បេះដូង",
    "ស្រាលាញ": "ស្រឡាញ់",  # love
    "ស្រលាញ់": "ស្រឡាញ់",
    "កំសត់": "កម្សត់",      # sad/sorrow
    "កំសាន្ត": "កម្សាន្ត",   # entertainment
    "សង្ខារ": "សង្សារ",     # sweetheart (often confused with Buddhist sankhara)
    "ប្រលឹម": "ព្រលឹម",     # dawn
    "ព្រលឹង": "ព្រលឹង",     # soul
    "រាត្រី": "រាត្រី",     # night
    "ដួងចន្ទ": "ដួងចន្ទ",   # moon
    "ដួងចិត្ត": "ដួងចិត្ត",   # heart/spirit
    "ទឹកភ្នែក": "ទឹកភ្នែក",  # tears
    "ស្នេហា": "ស្នេហា",     # love
}


def is_khmer_text(text: str) -> bool:
    """Checks if text contains Khmer Unicode characters (\u1780 - \u17FF)."""
    return any("\u1780" <= c <= "\u17FF" for c in text)


def normalize_unicode(text: str) -> str:
    """
    Standardize spaces and clean up zero-width non-joiners/spaces.
    Preserves Khmer coeng (subscript generator \u17D2).
    """
    if not text:
        return ""
    # Normalize multiple whitespace characters
    text = re.sub(r"[ \t]+", " ", text)
    # Remove repeated punctuation
    text = re.sub(r"([។៕?!\.,])\1+", r"\1", text)
    return text.strip()


def remove_repetitions(text: str, max_consecutive_repeats: int = 2) -> str:
    """
    Removes repetitive token or phrase loops caused by Whisper hallucinations
    e.g., 'បងស្រឡាញ់អូន បងស្រឡាញ់អូន បងស្រឡាញ់អូន' -> 'បងស្រឡាញ់អូន'
    """
    if not text:
        return ""

    tokens = text.split()
    if len(tokens) <= 2:
        return text

    # Word-level repetition check
    cleaned_tokens: List[str] = []
    repeat_count = 0
    last_token = None

    for t in tokens:
        if t == last_token:
            repeat_count += 1
            if repeat_count < max_consecutive_repeats:
                cleaned_tokens.append(t)
        else:
            last_token = t
            repeat_count = 0
            cleaned_tokens.append(t)

    result = " ".join(cleaned_tokens)

    # Multi-word phrase repetition check (2-4 words repeating consecutively)
    words = result.split()
    for phrase_len in range(4, 1, -1):
        if len(words) < phrase_len * 2:
            continue
        new_words: List[str] = []
        i = 0
        while i < len(words):
            phrase = words[i:i + phrase_len]
            next_phrase = words[i + phrase_len:i + 2 * phrase_len]
            if phrase == next_phrase and len(phrase) == phrase_len:
                new_words.extend(phrase)
                # Skip duplicate
                i += phrase_len
                # Skip further identical runs
                while i + phrase_len <= len(words) and words[i:i + phrase_len] == phrase:
                    i += phrase_len
            else:
                new_words.append(words[i])
                i += 1
        words = new_words

    return " ".join(words)


def correct_spelling(text: str, error_dict: Optional[Dict[str, str]] = None) -> str:
    """
    Replaces known Whisper Khmer transcription errors.
    """
    if not text:
        return ""

    fixes = DEFAULT_KHMER_FIXES.copy()
    if error_dict:
        fixes.update(error_dict)

    result = text
    for wrong, right in fixes.items():
        if wrong in result:
            result = result.replace(wrong, right)

    return result


def segment_words(text: str) -> List[str]:
    """
    Tokenizes text into words. Uses khmer-nltk for Khmer script,
    falling back to space-based splitting if khmer-nltk is unavailable.
    """
    if not text:
        return []
    if is_khmer_text(text) and _KHMER_NLTK_AVAILABLE and khmernltk:
        try:
            tokens = khmernltk.word_tokenize(text)
            if isinstance(tokens, list) and tokens:
                return [t.strip() for t in tokens if t.strip()]
        except Exception as e:
            log.debug(f"khmernltk segmentation failed: {e}")
    return text.split()


def post_process_khmer_text(
    text: str,
    error_dict: Optional[Dict[str, str]] = None,
    segment_with_spaces: bool = False,
) -> str:
    """
    Full pipeline to clean, correct, and optionally segment a Khmer text line.
    """
    if not text:
        return ""

    # 1. Unicode & whitespace normalization
    cleaned = normalize_unicode(text)

    # 2. Correct common spelling mistakes
    corrected = correct_spelling(cleaned, error_dict)

    # 3. Suppress repetitive hallucination loops
    de_duped = remove_repetitions(corrected)

    # 4. Optional word segmentation with spaces
    if segment_with_spaces and is_khmer_text(de_duped) and _KHMER_NLTK_AVAILABLE:
        tokens = segment_words(de_duped)
        if tokens:
            return " ".join(tokens)

    return de_duped


def post_process_segments(
    segments: List[Dict[str, Any]],
    error_dict: Optional[Dict[str, str]] = None,
    segment_with_spaces: bool = False,
) -> List[Dict[str, Any]]:
    """
    Applies post-processing to all transcription segments in place or returned as a new list.
    """
    processed = []
    for seg in segments:
        seg_copy = dict(seg)
        raw_text = seg_copy.get("text", "")
        clean_text = post_process_khmer_text(
            raw_text,
            error_dict=error_dict,
            segment_with_spaces=segment_with_spaces,
        )
        seg_copy["text"] = clean_text

        # Also apply word-level correction if words exist
        if seg_copy.get("words"):
            cleaned_words = []
            for w in seg_copy["words"]:
                w_copy = dict(w)
                w_text = w_copy.get("word", "")
                w_copy["word"] = correct_spelling(w_text, error_dict)
                cleaned_words.append(w_copy)
            seg_copy["words"] = cleaned_words

        processed.append(seg_copy)

    return processed
