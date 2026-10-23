"""
Aligning known lyric lines to the singer in a track, and saving the result next to the audio.

Every studio entry point that syncs lyrics (transcribe, verify, AI fix, paste-and-align)
goes through align_lyrics_to_audio, so they all measure timing the same way.
"""

import logging
import math
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException

from backend.lyric_engine import (
    detect_text_language,
    double_check_lyrics,
    export_lyrics_to_lrc,
    export_subtitles_to_srt,
    parse_subtitle_file,
)
from backend.paths import find_audio_file
from backend.vocal_align import force_align_lyrics_to_audio

log = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]

# Below this the acoustic model barely heard the words; the studio marks those lines for review.
LOW_LINE_CONFIDENCE = 0.4


class AlignmentError(HTTPException):
    """
    The lyrics could not be aligned to this audio. Subclasses HTTPException so an endpoint can let
    it propagate as a clean 4xx answer, and callers that fall back on failure can catch it by name.
    """


# --- Reading pasted lyrics -------------------------------------------------------------------

_LRC_TAG = re.compile(r'^\[(?:ti|ar|al|by|offset|length|re|ve):.*?\]', re.IGNORECASE)
_LIST_MARKER = re.compile(r'^(?:#+|\*+|-+|\d+[\.\)]|[A-Za-z]+\s*\d+:)\s*')
_LRC_TIME = re.compile(r'^\[\d{1,2}:\d{2}(?:\.\d+)?\]\s*')
_SRT_TIME = re.compile(r'^\d{2}:\d{2}(?:\.\d+)?\s*-->\s*\d{2}:\d{2}(?:\.\d+)?\s*')
_SPEAKER_TAG = re.compile(
    r'^\s*[\(\[]\s*(?:ស្រី|ប្រុស|ស្រីនិងប្រុស|ប្រុសនិងស្រី|រួមគ្នា|ស្រី/ប្រុស|ប្រុស/ស្រី|F|M|Male|Female|Singer)\s*[\)\]]\s*',
    re.IGNORECASE,
)
# Instrumental markers such as "((( ... ភ្លេង ... )))", "[Music]", "(Solo)"
_INSTRUMENTAL = re.compile(
    r'^\s*[\(\[\{<~-]*\s*(?:\.{2,}|…|-+|\*+)?\s*'
    r'(?:ភ្លេង|តន្ត្រី|music|solo|instrumental|guitar\s*solo|intro|outro|bridge)'
    r'\s*(?:\.{2,}|…|-+|\*+)?\s*[\)\]\}>~-]*\s*$',
    re.IGNORECASE,
)
_PUNCTUATION_ONLY = re.compile(r'^[()\[\]{}<>\s.…·\-–—~:;!?។៕,]+$')


def parse_reference_lyrics(text: str) -> List[str]:
    """
    The sung lines of pasted lyrics: drops LRC headers, timestamps, list markers, speaker tags,
    instrumental markers and punctuation-only lines, and keeps every real line in order.
    """
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or _LRC_TAG.match(line):
            continue
        line = _LIST_MARKER.sub('', line).strip()
        line = _LRC_TIME.sub('', line)
        line = _SRT_TIME.sub('', line)
        line = _SPEAKER_TAG.sub('', line).strip()
        if line and not _INSTRUMENTAL.match(line) and not _PUNCTUATION_ONLY.match(line):
            lines.append(line)
    return lines


# --- Locating the audio ----------------------------------------------------------------------

def require_audio_file(audio_path: Optional[str]) -> str:
    """The track to align against. Never guesses another song when the path is wrong."""
    if not audio_path:
        raise AlignmentError(status_code=400, detail="Select an audio track before syncing lyrics")
    found = find_audio_file(audio_path)
    if not found:
        raise AlignmentError(status_code=404, detail="Selected audio file not found")
    return found


# --- Aligning --------------------------------------------------------------------------------

def _clamp_line(line: Dict[str, Any], duration: float) -> None:
    """Keeps the line inside the track and its words in order inside the line."""
    start = float(line.get("start", 0.0))
    end = float(line.get("end", start + 2.0))
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration):
        start = max(0.0, min(start, max(0.0, duration - 0.4)))
        end = max(start + 0.35, min(end, duration if duration > 0 else start + 2.0))
    line["start"] = round(start, 2)
    line["end"] = round(end, 2)

    words = line.get("words", [])
    if not words:
        return
    cursor = line["start"]
    for word in words:
        ws = float(word.get("start", cursor))
        we = float(word.get("end", ws + 0.1))
        if not (math.isfinite(ws) and math.isfinite(we)):
            ws, we = cursor, cursor + 0.1
        ws = max(cursor, min(ws, max(cursor, line["end"] - 0.04)))
        we = max(ws + 0.04, min(we, line["end"]))
        word["start"] = round(ws, 2)
        word["end"] = round(we, 2)
        cursor = word["end"]
    if words[-1]["end"] > line["end"]:
        line["end"] = words[-1]["end"]


def align_lyrics_to_audio(
    lyrics: List[Dict[str, Any]],
    audio_path: str,
    progress_callback: Optional[ProgressCallback] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    """
    Times every line (and word) of `lyrics` against the singer in `audio_path`, keeping the text
    exactly as given. Returns (lines, report, source) where source is "ctc_word_alignment" when
    each word was matched acoustically, or "acoustic_estimate" when only phrases were found.
    """
    from backend.audio_analyzer import decode_audio_to_numpy
    from backend.vocal_align import detect_vocal_segments, get_cached_vocals_path

    report_progress = progress_callback or (lambda _pct, _msg: None)
    texts = [str(line.get("text", "")).strip() for line in lyrics]
    if not texts or not all(texts):
        raise AlignmentError(status_code=400, detail="Every lyric line must contain text")

    report_progress(30, "Reading the audio...")
    _, _, duration = decode_audio_to_numpy(audio_path, target_sr=8000)
    if get_cached_vocals_path(audio_path):
        report_progress(45, "Matching every word to the singer's voice...")
    else:
        report_progress(35, "Separating the voice from the music (first time for this song)...")

    aligned = force_align_lyrics_to_audio(texts, audio_path, duration)
    if not aligned or [line.get("text") for line in aligned] != texts:
        raise AlignmentError(
            status_code=422,
            detail="Could not align every original lyric line to this audio; lyrics were not replaced",
        )

    report_progress(85, "Checking the timing of every line...")
    verified, report = double_check_lyrics(aligned, preserve_text=True)
    if [line["text"] for line in verified] != texts:
        raise AlignmentError(status_code=422, detail="Alignment changed the original lines; lyrics were not replaced")

    for original, line, measured in zip(lyrics, verified, aligned):
        _clamp_line(line, duration)
        line["line_id"] = original.get("line_id", line.get("line_id", 0))
        if "confidence" in measured:
            line["confidence"] = measured["confidence"]

    word_aligned = all("confidence" in line for line in aligned)
    if not word_aligned and len(detect_vocal_segments(audio_path)) < 2:
        raise AlignmentError(status_code=422, detail="No reliable singing phrases detected; lyrics were not replaced")

    report.pop("confidence", None)
    report["status"] = "Timestamp structure checked; singing accuracy requires playback review"
    return verified, report, "ctc_word_alignment" if word_aligned else "acoustic_estimate"


def unsure_line_indexes(lines: List[Dict[str, Any]]) -> List[int]:
    """Lines the word aligner could barely hear, for the studio to flag for a playback check."""
    return [i for i, line in enumerate(lines) if line.get("confidence", 1.0) < LOW_LINE_CONFIDENCE]


# --- Saving ----------------------------------------------------------------------------------

def _bare_words(cues: List[Dict[str, Any]]) -> List[str]:
    # Caption parsers drop bracket punctuation, so compare bare words only.
    return [re.sub(r"[^\w\s]+", "", c["text"], flags=re.UNICODE).strip().lower() for c in cues]


def save_aligned_subtitles(lyrics: List[Dict[str, Any]], audio_path: str, force_replace_srt: bool = False) -> None:
    """
    Writes the .lrc (and .km.lrc for Khmer) next to the audio. An existing .srt is only replaced
    when it holds these same words, so a hand-made sheet is never overwritten, unless forced.
    """
    base = os.path.splitext(audio_path)[0]
    is_khmer = detect_text_language(" ".join(line["text"] for line in lyrics)) == "km"
    srt_content = export_subtitles_to_srt(lyrics)
    new_words = _bare_words(lyrics)
    for suffix in ("", ".km") if is_khmer else ("",):
        export_lyrics_to_lrc(lyrics, f"{base}{suffix}.lrc")
        srt_path = f"{base}{suffix}.srt"
        if not force_replace_srt and os.path.exists(srt_path):
            try:
                existing = _bare_words(parse_subtitle_file(srt_path))
            except Exception as e:
                log.warning(f"[Lyrics Align] Could not read {os.path.basename(srt_path)}: {e}")
                existing = None
            if existing != new_words:
                continue
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
