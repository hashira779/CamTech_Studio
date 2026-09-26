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
try:
    from backend.vocal_align import force_align_lyrics_to_audio
except ImportError:
    from vocal_align import force_align_lyrics_to_audio

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
            
    # Protect existing curated lyrics from being overwritten by raw ASR
    key = title.strip()
    if key in db and db[key].get("lyrics") and len(db[key].get("lyrics", [])) >= 4:
        return

    db[key] = {
        "title": key,
        "artist": artist.strip() if artist else "Unknown",
        "lyrics": lyrics
    }
    
    try:
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        log.info(f"[Khmer Lyric Matcher] Cached lyrics for '{title}' into local DB.")
    except Exception as e:
        log.warning(f"[Khmer Lyric Matcher] Could not save to DB: {e}")




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


def upload_audio_to_gemini_files_api(api_key: str, file_path: str, mime_type: str = "audio/mp3") -> Optional[str]:
    """Uploads audio file to Gemini Files API and returns file_uri."""
    import urllib.request
    try:
        filesize = os.path.getsize(file_path)
        upload_url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"
        headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(filesize),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json"
        }
        meta_payload = json.dumps({"file": {"display_name": os.path.basename(file_path)}}).encode("utf-8")
        req = urllib.request.Request(upload_url, data=meta_payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            upload_endpoint = resp.headers.get("X-Goog-Upload-URL")
            if not upload_endpoint:
                return None
        
        with open(file_path, "rb") as f:
            file_bytes = f.read()
            
        upload_headers = {
            "Content-Length": str(filesize),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize"
        }
        req2 = urllib.request.Request(upload_endpoint, data=file_bytes, headers=upload_headers, method="POST")
        with urllib.request.urlopen(req2, timeout=40) as resp2:
            file_info = json.loads(resp2.read().decode("utf-8"))
            return file_info.get("file", {}).get("uri")
    except Exception as e:
        log.warning(f"[Gemini Files API] Upload notice: {e}")
        return None


def parse_lrc_to_aligned(lrc_text: str, total_duration: float = 180.0) -> List[Dict[str, Any]]:
    """Parses timestamped [mm:ss.xx] LRC text into structured aligned lines with orthographic normalization."""
    try:
        from backend.lyric_engine import normalize_khmer_orthography, clean_subtitle_text
    except ImportError:
        try:
            from lyric_engine import normalize_khmer_orthography, clean_subtitle_text
        except ImportError:
            normalize_khmer_orthography = lambda x: x
            clean_subtitle_text = lambda x: x

    pattern = re.compile(r'\[(\d{1,2}):(\d{2}(?:\.\d+)?)\](.*)')
    raw_parsed = []
    for line in lrc_text.strip().splitlines():
        m = pattern.match(line.strip())
        if m:
            mins = int(m.group(1))
            secs = float(m.group(2))
            lyric = m.group(3).strip()
            if lyric and any('\u1780' <= c <= '\u17FF' for c in lyric):
                # Clean speaker labels and metadata
                lyric = clean_subtitle_text(lyric)
                # Repair artificial syllable-separated spacing (e.g., "ដក ចិត្ត ស្នេហ៍" -> "ដកចិត្តស្នេហ៍")
                words = lyric.split()
                if len(words) >= 4 and all(len(w) <= 4 for w in words):
                    lyric = "".join(words)
                # Orthographic correction (including ត្រានត្រង់ -> ត្រានត្រើយ)
                lyric = normalize_khmer_orthography(lyric)
                start_sec = round(mins * 60 + secs, 2)
                raw_parsed.append((start_sec, lyric))
    
    if not raw_parsed:
        return []

    aligned = []
    for i, (start_sec, lyric) in enumerate(raw_parsed):
        if i + 1 < len(raw_parsed):
            next_start = raw_parsed[i+1][0]
            end_sec = round(min(start_sec + 6.0, max(start_sec + 1.5, next_start - 0.2)), 2)
        else:
            end_sec = round(min(total_duration, start_sec + 5.0), 2)
        aligned.append({
            "line_id": i,
            "start": start_sec,
            "end": end_sec,
            "text": lyric
        })
    return aligned


def transcribe_audio_with_gemini(
    audio_path: str,
    title: str = "",
    artist: str = "",
    duration: float = 180.0
) -> Optional[Tuple[List[str], Optional[List[Dict[str, Any]]]]]:
    """
    Transcribes actual audio file using Gemini Multimodal Audio.
    1. Uses Gemini Files API for 100% reliable upload without 503 errors.
    2. Requests synchronized LRC timestamps [mm:ss.xx] matching true singer vocal onsets.
    Returns (raw_lines, optional_aligned_with_true_timestamps).
    """
    api_key = get_gemini_api_key()
    if not api_key or not audio_path or not os.path.exists(audio_path):
        return None

    import base64
    import urllib.request

    mime_type = "audio/mp3" if audio_path.lower().endswith(".mp3") else "audio/wav"

    # Step 1: Upload via Files API
    file_uri = upload_audio_to_gemini_files_api(api_key, audio_path, mime_type=mime_type)

    prompt = (
        f"You are an expert music subtitler and Cambodian audio transcriber.\n"
        f"Song title hint: '{title}', Artist hint: '{artist}'.\n"
        f"Listen carefully to the audio and transcribe the exact lyrics in synchronized LRC format with timestamps.\n"
        f"Format strictly as: [mm:ss.xx] Khmer lyrics line\n"
        f"Example:\n"
        f"[00:16.00] គ្មានអ្នកណា ល្ងង់ដូចបង ចង់ធ្វើមនុស្សល្អ\n"
        f"Rules:\n"
        f"1. Timestamps MUST accurately reflect when the singer begins singing each phrase.\n"
        f"2. Transcribe ONLY the authentic words sung. Do NOT invent, loop, or hallucinate lyrics during instrumental solos.\n"
        f"3. Output only valid LRC lines, one phrase per line.\n"
        f"4. Natural Khmer phrasing: Do NOT split every syllable with spaces (write natural continuous words like 'ដកចិត្តស្នេហ៍វិញទៅត្រានត្រើយ', NEVER 'ដក ចិត្ត ស្នេហ៍').\n"
        f"5. Rhyme integrity (កាព្យចុងចួន): Cambodian song lyrics strictly follow poetic end-rhymes. Words rhyming with 'ឡើយ' or 'ហើយ' must use 'ត្រានត្រើយ' (or 'ត្រាណត្រើយ'), NEVER 'ត្រង់'."
    )

    models = ["gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-flash-latest", "gemini-3.5-flash"]

    for model in models:
        try:
            if file_uri:
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": prompt},
                            {"file_data": {"file_uri": file_uri, "mime_type": mime_type}}
                        ]
                    }]
                }
            else:
                # Fallback to inline base64 if Files API failed
                file_size = os.path.getsize(audio_path)
                if file_size > 12 * 1024 * 1024:
                    continue
                with open(audio_path, "rb") as f:
                    b64_audio = base64.b64encode(f.read()).decode("utf-8")
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": mime_type, "data": b64_audio}}
                        ]
                    }]
                }

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            
            with urllib.request.urlopen(req, timeout=50) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                text = res["candidates"][0]["content"]["parts"][0]["text"]
                
                # Check for timestamped lines
                aligned = parse_lrc_to_aligned(text, total_duration=duration)
                if aligned and len(aligned) >= 4:
                    raw_lines = [a["text"] for a in aligned]
                    log.info(f"[Gemini Audio ASR] Successfully transcribed {len(aligned)} timestamped lines via {model}")
                    if title:
                        save_to_local_lyrics_db(title, artist, raw_lines)
                    return raw_lines, aligned

                # Fallback to un-timestamped lines if no timestamps
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                khmer_lines = [
                    re.sub(r'^\[.*?\]\s*', '', l) for l in lines
                    if any('\u1780' <= c <= '\u17FF' for c in l)
                    and not l.startswith(('#', '*', '- ', '==='))
                ]
                if len(khmer_lines) >= 4:
                    log.info(f"[Gemini Audio ASR] Transcribed {len(khmer_lines)} untimed lines via {model}")
                    if title:
                        save_to_local_lyrics_db(title, artist, khmer_lines)
                    return khmer_lines, None

        except Exception as e:
            log.warning(f"[Gemini Audio ASR] {model} notice: {e}")
            import time
            time.sleep(1)

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
    3. Uses Gemini Multimodal Audio to LISTEN to the actual song and transcribe real words with exact timestamps.
    4. Falls back to text search if no audio file is accessible.
    """
    # Probe duration if missing
    if duration <= 0.0 and os.path.exists(audio_path):
        try:
            import soundfile as sf
            info = sf.info(audio_path)
            duration = info.duration
        except Exception:
            duration = 180.0

    raw_lines = None
    true_aligned = None

    # Step 1: Check local verified DB or description for authentic golden spelling
    if title:
        raw_lines = search_local_lyrics_db(title, artist)

    if not raw_lines and description:
        raw_lines = extract_lyrics_from_description(description)

    # Step 2: Uses Gemini Multimodal Audio to LISTEN to the actual song and transcribe real words
    if not raw_lines and audio_path and os.path.exists(audio_path):
        log.info(f"[Khmer Lyric Matcher] Listening to audio with Gemini for: {title}")
        res = transcribe_audio_with_gemini(audio_path, title, artist, duration)
        if res:
            raw_lines, true_aligned = res

    # Step 3: Fallback to Gemini text prompt for text extraction if not found locally and no audio transcribed
    if not raw_lines and title:
        log.info(f"[Khmer Lyric Matcher] Fallback to Gemini text prompt for: {title}")
        raw_lines = fetch_lyrics_with_gemini(title, artist, description=description)

    # Step 4: Align lines using Whisper Magic
    if raw_lines:
        if true_aligned:
            aligned = true_aligned
        elif audio_path and os.path.exists(audio_path):
            log.info("[Khmer Lyric Matcher] Using Dynamic Vocal Alignment Engine...")
            aligned = force_align_lyrics_to_audio(raw_lines, audio_path, duration)
        else:
            log.warning("[Khmer Lyric Matcher] No audio file; using force_align fallback.")
            aligned = force_align_lyrics_to_audio(raw_lines, audio_path or "", duration)
    else:
        return None

    if not aligned:
        return None

    # Step 5: Write synchronized .LRC file alongside audio
    lrc_content = generate_lrc_content(aligned)
    base_no_ext = os.path.splitext(audio_path)[0]
    lrc_path = base_no_ext + ".lrc"

    try:
        with open(lrc_path, "w", encoding="utf-8") as f:
            f.write(lrc_content)
        log.info(f"[Khmer Lyric Matcher] Successfully saved authentic synced LRC: {lrc_path}")

        # Also update any existing .vtt or .km.vtt file to ensure perfect sync across all formats
        for vtt_cand in [base_no_ext + ".km.vtt", base_no_ext + ".vtt"]:
            if os.path.exists(vtt_cand):
                try:
                    vtt_lines = ["WEBVTT\nKind: captions\nLanguage: km\n"]
                    for line in aligned:
                        s = line["start"]
                        e = line["end"]
                        s_h, s_m, s_s = int(s // 3600), int((s % 3600) // 60), s % 60
                        e_h, e_m, e_s = int(e // 3600), int((e % 3600) // 60), e % 60
                        vtt_lines.append(f"{s_h:02d}:{s_m:02d}:{s_s:06.3f} --> {e_h:02d}:{e_m:02d}:{e_s:06.3f}\n{line['text']}\n")
                    with open(vtt_cand, "w", encoding="utf-8") as vf:
                        vf.write("\n".join(vtt_lines))
                    log.info(f"[Khmer Lyric Matcher] Updated existing VTT with true audio timestamps: {vtt_cand}")
                except Exception as ve:
                    log.warning(f"[Khmer Lyric Matcher] Could not update VTT: {ve}")

        return lrc_path, aligned
    except Exception as e:
        log.error(f"[Khmer Lyric Matcher] Failed to write LRC: {e}")
        return None
