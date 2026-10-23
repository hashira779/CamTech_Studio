"""
Lyrics and subtitle endpoints: parse, load, save, verify, AI-fix, and align lyrics to the singer.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.lyric_engine import (
    double_check_lyrics,
    export_lyrics_to_lrc,
    export_subtitles_to_srt,
    find_matching_subtitles,
    parse_subtitle_content,
    parse_subtitle_file,
)
from backend.paths import find_audio_file_or_latest
from backend.progress import transcribe_progress, update_transcribe_progress
from backend.services.lyric_alignment import (
    align_lyrics_to_audio,
    parse_reference_lyrics,
    require_audio_file,
    save_aligned_subtitles,
    unsure_line_indexes,
)

log = logging.getLogger(__name__)
router = APIRouter()


class LrcParseRequest(BaseModel):
    lrc_text: str


class LyricsVerifyRequest(BaseModel):
    lyrics_data: List[Dict[str, Any]]
    audio_path: Optional[str] = None


class LyricsCorrectReferenceRequest(BaseModel):
    lyrics_data: Optional[List[Dict[str, Any]]] = None
    reference_text: str
    audio_path: Optional[str] = None


class SubtitleSaveRequest(BaseModel):
    lyrics_data: List[Dict[str, Any]]
    audio_path: Optional[str] = None


class SubtitleAIFixRequest(BaseModel):
    lyrics_data: List[Dict[str, Any]]
    audio_path: Optional[str] = None
    align_vocals: Optional[bool] = False


def _structure_only_check(lyrics: List[Dict[str, Any]]):
    """Orders and bounds timestamps without listening to the audio."""
    verified, report = double_check_lyrics(lyrics, preserve_text=True)
    report.pop("confidence", None)
    report["status"] = "Timestamp structure checked; no singer audio was checked"
    return verified, report


# --- Progress --------------------------------------------------------------------------------

@router.get("/api/transcribe/progress")
def get_transcribe_progress():
    """Stage and percentage of the running transcribe or align job."""
    return transcribe_progress()


# --- Parse and load --------------------------------------------------------------------------

@router.post("/api/parse-lrc")
async def parse_lrc(req: LrcParseRequest):
    """Parses LRC, SRT, or VTT lyrics with word-level interpolation and Khmer tokenization."""
    try:
        lyrics = parse_subtitle_content(req.lrc_text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LRC parse failed: {e}")
    return {"status": "success", "lyrics": lyrics, "count": len(lyrics)}


@router.post("/api/lyrics/upload")
async def upload_lyrics_file(file: UploadFile = File(...)):
    """Uploads and parses an LRC, SRT, or VTT subtitle file."""
    try:
        content = (await file.read()).decode("utf-8", errors="ignore")
        lyrics = parse_subtitle_content(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse uploaded subtitle file: {e}")
    return {"status": "success", "filename": file.filename, "lyrics": lyrics, "count": len(lyrics)}


@router.get("/api/subtitles")
def get_subtitles_api(audio_path: Optional[str] = None):
    """Loads the subtitles (.srt / .lrc) saved next to the given track."""
    not_found = {"status": "not_found", "lyrics": [], "count": 0}
    audio_p = find_audio_file_or_latest(audio_path)
    if not audio_p:
        return not_found
    sub_path = find_matching_subtitles(audio_p)
    if not sub_path or not os.path.exists(sub_path):
        return not_found
    lyrics = parse_subtitle_file(sub_path)
    return {"status": "success", "file": sub_path, "count": len(lyrics), "lyrics": lyrics}


@router.post("/api/subtitles/save")
async def save_subtitles_api(req: SubtitleSaveRequest):
    """Saves edited cues to the companion .lrc and .srt files."""
    audio_p = find_audio_file_or_latest(req.audio_path)
    if not (audio_p and req.lyrics_data):
        return {"status": "ok", "count": len(req.lyrics_data or [])}
    base = os.path.splitext(audio_p)[0]
    try:
        for ext in (".lrc", ".km.lrc"):
            export_lyrics_to_lrc(req.lyrics_data, f"{base}{ext}")
        srt = export_subtitles_to_srt(req.lyrics_data)
        for ext in (".srt", ".km.srt"):
            with open(f"{base}{ext}", "w", encoding="utf-8") as f:
                f.write(srt)
    except Exception as e:
        log.error(f"[Subtitles] Save failed for {os.path.basename(base)}: {e}")
        return {"status": "error", "detail": str(e)}
    return {"status": "success", "file": base, "count": len(req.lyrics_data)}


# --- Verify and fix --------------------------------------------------------------------------

@router.post("/api/lyrics/verify")
def verify_lyrics_api(req: LyricsVerifyRequest):
    """Re-measures timing against the singer when a track is given, else checks structure only."""
    lyrics = req.lyrics_data or []
    try:
        if req.audio_path:
            audio_p = require_audio_file(req.audio_path)
            verified, report, source = align_lyrics_to_audio(lyrics, audio_p)
            save_aligned_subtitles(verified, audio_p)
        else:
            verified, report = _structure_only_check(lyrics)
            source = "timestamp_validation"
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lyrics verification error: {e}")
    return {
        "status": "success",
        "verified": True,
        "source": source,
        "lines_count": len(verified),
        "words_count": report.get("total_words", 0),
        "corrections_made": report.get("corrections_count", 0),
        "report": report,
        "lyrics": verified,
        "srt_content": export_subtitles_to_srt(verified),
    }


@router.post("/api/lyrics/auto_fix")
def auto_fix_lyrics_api(req: LyricsVerifyRequest):
    """Lets the LLM fix phonetic and contextual transcription errors, then re-checks timing."""
    from backend.llm_engine import llm_engine
    try:
        llm_fixed = llm_engine.auto_correct_transcription(req.lyrics_data)
        verified, report = double_check_lyrics(llm_fixed)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Auto-Fix Error: {e}")
    return {"status": "success", "verified": True, "lyrics": verified, "report": report}


@router.post("/api/subtitles/ai-fix")
def ai_fix_subtitles_api(req: SubtitleAIFixRequest):
    """
    Repairs phonetic and Khmer spelling errors with the LLM, then re-times the lines against the
    singer when align_vocals is set (otherwise only orders and bounds the timestamps).
    """
    lyrics = req.lyrics_data or []
    if not lyrics:
        return {"status": "success", "verified": True, "lyrics": [], "report": {}, "count": 0}

    from backend.llm_engine import llm_engine
    try:
        llm_fixed = llm_engine.auto_correct_transcription(lyrics)
    except Exception as e:
        log.warning(f"[AI Subtitle Fix] LLM step skipped: {e}")
        llm_fixed = lyrics

    try:
        if req.align_vocals:
            audio_p = require_audio_file(req.audio_path)
            verified, report, source = align_lyrics_to_audio(llm_fixed, audio_p)
            save_aligned_subtitles(verified, audio_p)
        else:
            verified, report = _structure_only_check(llm_fixed)
            source = "timestamp_validation"
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Subtitle Fix failed: {e}")
    return {
        "status": "success",
        "verified": True,
        "source": source,
        "count": len(verified),
        "corrections_made": report.get("corrections_count", 0),
        "report": report,
        "lyrics": verified,
        "srt_content": export_subtitles_to_srt(verified),
    }


# --- Align to the singer ---------------------------------------------------------------------

@router.post("/api/subtitles/align-audio")
def align_subtitles_to_audio_api(req: SubtitleAIFixRequest):
    """Re-times the loaded lines against the singer, keeping their text."""
    if not req.lyrics_data:
        raise HTTPException(status_code=400, detail="Load lyrics before syncing")
    audio_p = require_audio_file(req.audio_path)
    try:
        verified, report, source = align_lyrics_to_audio(req.lyrics_data, audio_p)
        save_aligned_subtitles(verified, audio_p)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vocal subtitle alignment error: {e}")
    return {
        "status": "success",
        "source": source,
        "count": len(verified),
        "lyrics": verified,
        "report": report,
        "srt_content": export_subtitles_to_srt(verified),
    }


@router.post("/api/lyrics/correct-with-reference")
def correct_lyrics_with_reference_api(req: LyricsCorrectReferenceRequest):
    """
    Replaces the loaded lines with pasted original lyrics and times them against the singer.
    Answers which lines the aligner was unsure about, so the studio can flag them for review.
    """
    started = time.time()
    if not req.reference_text or not req.reference_text.strip():
        raise HTTPException(status_code=400, detail="Please paste reference lyrics text")
    audio_p = require_audio_file(req.audio_path)
    lines = parse_reference_lyrics(req.reference_text)
    if not lines:
        raise HTTPException(status_code=400, detail="No readable lyric lines found in pasted text")

    log.info(f"[Lyrics Align] Aligning {len(lines)} pasted lines to '{os.path.basename(audio_p)}'")
    update_transcribe_progress(10, f"Read {len(lines)} lyric lines")
    try:
        aligned, report, source = align_lyrics_to_audio(
            [{"text": text} for text in lines], audio_p, progress_callback=update_transcribe_progress
        )
        save_aligned_subtitles(aligned, audio_p, force_replace_srt=True)
    except Exception as e:
        update_transcribe_progress(0, f"Error: {getattr(e, 'detail', e)}")
        log.error(f"[Lyrics Align] Failed after {time.time() - started:.1f}s: {getattr(e, 'detail', e)}")
        raise

    unsure = unsure_line_indexes(aligned)
    update_transcribe_progress(100, f"Aligned {len(aligned)} lines")
    log.info(f"[Lyrics Align] Aligned {len(aligned)} lines in {time.time() - started:.1f}s "
             f"({source}, {len(unsure)} to check)")
    return {
        "status": "success",
        "lines_count": len(aligned),
        "changes_count": len(aligned),
        "source": source,
        "report": report,
        "unsure_lines": unsure,
        "lyrics": aligned,
    }
