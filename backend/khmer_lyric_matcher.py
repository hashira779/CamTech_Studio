"""
Khmer Lyric Matcher & Auto-Fetcher for VIDA.
Solves the 1M songs problem:
1. Automatically extracts human-written lyrics from YouTube descriptions or metadata.
2. Checks local and cached verified Khmer lyrics database.
3. Automatically generates synchronized LRC files with intelligent phrase pacing.
4. Bypasses inaccurate, garbled speech-to-text / YouTube auto-captions.
"""

import os
import re
import json
import logging
from typing import List, Dict, Any, Optional, Tuple

log = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "khmer_lyrics_db.json")


def normalize_title_for_lookup(title: str) -> str:
    """Normalizes Khmer title for fuzzy lookup by removing punctuation and whitespace."""
    if not title:
        return ""
    # Strip common bracketed noise
    t = re.sub(r'\[.*?\]|\(.*?\)|【.*?】', '', title)
    t = re.sub(r'[\s|I]+(?:Video\s*Animation|Official.*|MV|Audio|Full\s*Audio|Remix)$', '', t, flags=re.IGNORECASE)
    # Remove Khmer and Latin punctuation
    t = re.sub(r'[\s\-_:៖។៕,.·\'"]+', '', t).strip().lower()
    return t


def extract_lyrics_from_description(description: str) -> Optional[List[str]]:
    """
    Extracts authentic lyrics if the uploader pasted them in the YouTube description.
    Detects Khmer poetic stanzas and lines.
    """
    if not description or not any('\u1780' <= c <= '\u17FF' for c in description):
        return None

    lines = [line.strip() for line in description.splitlines() if line.strip()]
    
    # Check for lyric block indicators
    lyric_started = False
    candidate_lines = []
    
    lyric_headers = [
        r'ទំនុកច្រៀង', r'ទំនុកភ្លេង', r'ច្រៀងដោយ', r'lyrics?', r'lyric video',
        r'បទចម្រៀង', r'មរតកដើម', r'verse', r'chorus'
    ]
    header_pattern = re.compile(r'(' + '|'.join(lyric_headers) + r')\s*[:៖\-]', re.IGNORECASE)
    
    for line in lines:
        # Filter out links, channel promos, credits
        if re.search(r'https?://|www\.|facebook|telegram|subscribe|copyright|រក្សាសិទ្ធិ|ផលិតកម្ម', line, re.IGNORECASE):
            continue
        
        # Check if line indicates lyric start
        if header_pattern.search(line):
            lyric_started = True
            continue
            
        # If in lyric block or line is a pure Khmer song line (4 to 15 Khmer words)
        khmer_chars = [c for c in line if '\u1780' <= c <= '\u17FF']
        if len(khmer_chars) >= 10:
            # Looks like a singing verse line
            candidate_lines.append(line)
            
    # If we collected a reasonable number of lyrical lines (at least 6 lines)
    if len(candidate_lines) >= 6:
        log.info(f"[Khmer Lyric Matcher] Extracted {len(candidate_lines)} lyric lines from video description!")
        return candidate_lines
        
    return None


def search_local_lyrics_db(title: str, artist: str = "") -> Optional[List[str]]:
    """Looks up song in local verified lyrics database."""
    if not os.path.exists(DB_PATH):
        return None
        
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            db = json.load(f)
            
        norm_query = normalize_title_for_lookup(title)
        
        # 1. Exact match on normalized title
        for key, entry in db.items():
            if normalize_title_for_lookup(key) == norm_query:
                return entry.get("lyrics", [])
            if normalize_title_for_lookup(entry.get("title", "")) == norm_query:
                return entry.get("lyrics", [])
                
        # 2. Substring match
        for key, entry in db.items():
            norm_key = normalize_title_for_lookup(key)
            if norm_key and (norm_key in norm_query or norm_query in norm_key):
                return entry.get("lyrics", [])
                
    except Exception as e:
        log.warning(f"[Khmer Lyric Matcher] DB lookup error: {e}")
        
    return None


def save_to_local_lyrics_db(title: str, artist: str, lyrics: List[str]):
    """Caches newly verified lyrics into local database."""
    if not title or not lyrics:
        return
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = {}
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                db = json.load(f)
        except Exception:
            db = {}
            
    db[title.strip()] = {
        "title": title.strip(),
        "artist": artist.strip() if artist else "Unknown",
        "lyrics": lyrics
    }
    
    try:
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        log.info(f"[Khmer Lyric Matcher] Cached lyrics for '{title}' into local DB.")
    except Exception as e:
        log.warning(f"[Khmer Lyric Matcher] Could not save to DB: {e}")


def align_lyrics_to_audio_duration(
    lyrics: List[str],
    duration: float,
    intro_lead: float = 16.0,
    outro_tail: float = 12.0
) -> List[Dict[str, Any]]:
    """
    Intelligently spaces out authentic lyric lines across audio duration.
    Calculates start and end timestamps proportionally to line length.
    """
    if not lyrics:
        return []
        
    if duration <= 30.0:
        intro_lead = 2.0
        outro_tail = 2.0
        
    singing_duration = max(10.0, duration - intro_lead - outro_tail)
    
    # Calculate relative weights based on character lengths
    lengths = [max(4, len(line.replace(" ", ""))) for line in lyrics]
    total_length = sum(lengths)
    
    aligned_lines = []
    current_time = intro_lead
    
    for idx, (line, length) in enumerate(zip(lyrics, lengths)):
        line_duration = max(2.5, (length / total_length) * singing_duration)
        start_time = round(current_time, 2)
        end_time = round(current_time + line_duration, 2)
        
        aligned_lines.append({
            "line_id": idx,
            "start": start_time,
            "end": end_time,
            "text": line
        })
        current_time = end_time
        
    return aligned_lines


def generate_lrc_content(aligned_lines: List[Dict[str, Any]]) -> str:
    """Formats aligned lines into standard .LRC format."""
    out = []
    for line in aligned_lines:
        start_sec = line["start"]
        mins = int(start_sec // 60)
        secs = start_sec % 60
        out.append(f"[{mins:02d}:{secs:05.2f}]{line['text']}")
    return "\n".join(out)


def match_or_fetch_khmer_lyrics(
    audio_path: str,
    title: str,
    artist: str = "",
    duration: float = 0.0,
    description: str = ""
) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """
    Main orchestration entry point:
    Attempts to match authentic lyrics before falling back to ASR.
    Returns (lrc_file_path, parsed_lyrics_list) or None.
    """
    raw_lines = None
    
    # Step 1: Check YouTube description
    if description:
        raw_lines = extract_lyrics_from_description(description)
        
    # Step 2: Check local verified DB
    if not raw_lines and title:
        raw_lines = search_local_lyrics_db(title, artist)
        
    if not raw_lines:
        return None
        
    # If duration wasn't passed, probe it
    if duration <= 0.0 and os.path.exists(audio_path):
        try:
            import soundfile as sf
            info = sf.info(audio_path)
            duration = info.duration
        except Exception:
            duration = 180.0  # default 3 min
            
    # Step 3: Align lines
    aligned = align_lyrics_to_audio_duration(raw_lines, duration)
    if not aligned:
        return None
        
    # Step 4: Write .LRC file alongside audio
    lrc_content = generate_lrc_content(aligned)
    base_no_ext = os.path.splitext(audio_path)[0]
    lrc_path = base_no_ext + ".lrc"
    
    try:
        with open(lrc_path, "w", encoding="utf-8") as f:
            f.write(lrc_content)
        log.info(f"[Khmer Lyric Matcher] Successfully saved authentic synced LRC: {lrc_path}")
        return lrc_path, aligned
    except Exception as e:
        log.error(f"[Khmer Lyric Matcher] Failed to write LRC: {e}")
        return None
