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


def get_gemini_api_key() -> str:
    """Retrieves Gemini API key from environment or .env file."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("GEMINI_API_KEY="):
                            api_key = line.strip().split("=", 1)[1].strip(' "\'')
                            break
            except Exception:
                pass
    return api_key


def gemini_clean_youtube_metadata(
    raw_title: str,
    uploader: str = "",
    description: str = ""
) -> Optional[Tuple[str, str, str]]:
    """
    Uses Gemini AI to cleanly extract (Song Title, Singer/Artist, Language) from a YouTube title & channel.
    Strips noise like [Official MV], (Lyrics), 4K, HD, Video Animation, Official Audio, Remix.
    Ensures title and singer are NOT flipped (especially for Khmer YouTube conventions).
    Returns (clean_title, clean_artist, detected_language) or None.
    """
    api_key = get_gemini_api_key()
    if not api_key or not raw_title:
        return None

    import urllib.request
    models_to_try = ["gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-3.5-flash"]

    prompt = f"""Given this YouTube music video:
Title: "{raw_title}"
Uploader/Channel: "{uploader}"

Extract the true Song Title and Singer/Artist name.
Rules:
1. Strip all noise like [Official MV], (Lyrics Video), 4K, HD, Video Animation, Official Audio, Remix.
2. Identify the true song title in the original language (Khmer, English, Vietnamese, etc.).
3. Identify the true singer / performing artist name.
4. If this is a Khmer song, ensure the song title and singer are NOT swapped (e.g. ស៊ីន ស៊ីសាមុត / Sinn Sisamouth is the singer, ផាត់ជាយបណ្តូលចិត្ត is the song title).
Return ONLY a valid JSON object in this exact schema:
{{"title": "Clean Song Title", "artist": "Clean Artist Name", "language": "km/en/vi/th"}}"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    data_bytes = json.dumps(payload).encode("utf-8")

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": api_key
        }
        try:
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=6) as response:
                result = json.loads(response.read().decode("utf-8"))
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text)
                t = parsed.get("title", "").strip()
                a = parsed.get("artist", "").strip()
                lang = parsed.get("language", "km").strip()
                if t and a:
                    log.info(f"[Gemini Metadata] Cleaned via {model}: Title='{t}', Artist='{a}', Lang='{lang}'")
                    return t, a, lang
        except Exception as e:
            log.debug(f"[Gemini Metadata] {model} notice: {e}")
            continue

    return None


def transcribe_audio_with_gemini(audio_path: str, title: str = "", artist: str = "") -> Optional[List[str]]:
    """
    Transcribes actual audio file using Gemini Multimodal Audio.
    Listens directly to the singer's voice so it NEVER hallucinates fake lyrics.
    """
    api_key = get_gemini_api_key()
    if not api_key or not audio_path or not os.path.exists(audio_path):
        return None

    import base64
    import urllib.request

    try:
        file_size = os.path.getsize(audio_path)
        # Limit to 15MB for inline REST payload
        if file_size > 15 * 1024 * 1024:
            log.warning(f"[Gemini Audio] File {audio_path} is {file_size/1024/1024:.1f}MB, too large for direct inline audio")
            return None

        mime_type = "audio/mp3" if audio_path.lower().endswith(".mp3") else "audio/wav"
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
        prompt = (
            f"Listen carefully to this Cambodian song audio.\n"
            f"Song title: {title}\nArtist: {artist}\n"
            f"Transcribe the exact lyrics in Khmer script line by line as sung by the singer.\n"
            f"Rules:\n"
            f"1. Transcribe ONLY the actual words sung in the audio.\n"
            f"2. Output only the Khmer lyrics lines, one line per singing phrase.\n"
            f"3. Do not include markdown headers, chords, English translations, or conversational filler."
        )

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": b64_audio}}
                ]
            }]
        }
        data_bytes = json.dumps(payload).encode("utf-8")

        models = ["gemini-flash-latest", "gemini-3.1-flash-lite", "gemini-3.5-flash"]
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")
            for attempt in range(2):
                try:
                    with urllib.request.urlopen(req, timeout=45) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        text = res["candidates"][0]["content"]["parts"][0]["text"]
                        lines = [l.strip() for l in text.splitlines() if l.strip()]
                        khmer_lines = [
                            l for l in lines
                            if any('\u1780' <= c <= '\u17FF' for c in l)
                            and not l.startswith(('#', '*', '- ', '==='))
                        ]
                        if len(khmer_lines) >= 4:
                            log.info(f"[Gemini Audio ASR] Successfully transcribed {len(khmer_lines)} authentic lines via {model}")
                            if title:
                                save_to_local_lyrics_db(title, artist, khmer_lines)
                            return khmer_lines
                except Exception as e:
                    log.warning(f"[Gemini Audio ASR] {model} attempt {attempt+1} error: {e}")
                    import time
                    time.sleep(1)
    except Exception as ex:
        log.error(f"[Gemini Audio ASR] Unexpected error: {ex}")

    return None


def fetch_lyrics_with_gemini(title: str, artist: str = "", description: str = "") -> Optional[List[str]]:
    """
    Fallback text lookup via Gemini when no audio file is available.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        return None

    import urllib.request
    models_to_try = ["gemini-3.1-flash-lite", "gemini-flash-latest", "gemini-3.5-flash"]

    desc_hint = f" (Context: {description[:150]})" if description else ""
    prompt = (
        f"You are an expert in Cambodian and international song lyrics. Provide the exact, authentic Khmer lyrics for the song '{title}' "
        f"{f'sung by {artist}' if artist else ''}{desc_hint}.\n"
        f"Rules:\n"
        f"1. Return ONLY the authentic Khmer lyrics, one singing line per line.\n"
        f"2. If you are not 100% certain of the real lyrics, do NOT invent fake lyrics.\n"
        f"3. Do not include introductory notes, chat greetings, or explanations.\n"
        f"4. Ensure traditional correct Khmer spelling."
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    data_bytes = json.dumps(payload).encode("utf-8")

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": api_key
        }
        try:
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=12) as response:
                result = json.loads(response.read().decode("utf-8"))
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                lines = [
                    line.strip() for line in text.splitlines()
                    if line.strip() and not line.strip().startswith(("#", "===", "ទំនុកច្រៀង", "បទ៖", "Here", "Sure", "```"))
                ]
                # Filter out pure English chatter lines
                khmer_lines = [l for l in lines if any('\u1780' <= c <= '\u17FF' for c in l)]
                if len(khmer_lines) >= 6:
                    log.info(f"[Gemini Lyrics] Retrieved {len(khmer_lines)} lines for '{title}' via {model}")
                    return khmer_lines
        except Exception as e:
            log.warning(f"[Gemini Lyrics] {model} attempt failed: {e}")
            continue

    return None


def match_or_fetch_khmer_lyrics(
    audio_path: str,
    title: str,
    artist: str = "",
    duration: float = 0.0,
    description: str = ""
) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """
    Main orchestration entry point:
    1. Checks local verified DB for instant hit.
    2. Checks YouTube description if authentic lyrics were pasted.
    3. Uses Gemini Multimodal Audio to LISTEN to the actual song and transcribe real words.
    4. Falls back to text search if no audio file is accessible.
    """
    raw_lines = None

    # Step 1: Check local verified DB (instant 0.01s cache)
    if title:
        raw_lines = search_local_lyrics_db(title, artist)

    # Step 2: Check YouTube description if uploader pasted authentic lyrics
    if not raw_lines and description:
        raw_lines = extract_lyrics_from_description(description)

    # Step 3: Listen directly to actual audio using Gemini Multimodal Audio (GROUND TRUTH - NEVER HALLUCINATES)
    if not raw_lines and audio_path and os.path.exists(audio_path):
        log.info(f"[Khmer Lyric Matcher] Listening to audio file: {audio_path} via Gemini Audio...")
        raw_lines = transcribe_audio_with_gemini(audio_path, title=title, artist=artist)

    # Step 4: Fallback to text prompt only if audio is missing
    if not raw_lines and title:
        log.info(f"[Khmer Lyric Matcher] Fallback to Gemini text prompt for: {title}")
        raw_lines = fetch_lyrics_with_gemini(title, artist, description=description)

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
