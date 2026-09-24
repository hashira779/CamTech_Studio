"""
Lyric Engine Module for VIDA
Supports automatic AI transcription with word-level timestamps using Whisper,
LRC/VTT/SRT subtitle file parsing with Khmer tokenization, and frame-time karaoke synchronization.
"""

import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
import re
import html
from typing import List, Dict, Any, Optional

# Safe import of Khmer word segmentation engine
try:
    from khmernltk import word_tokenize as khmer_word_tokenize
except ImportError:
    khmer_word_tokenize = None


def is_khmer_text(text: str) -> bool:
    """Checks if text contains Khmer Unicode characters."""
    return any('\u1780' <= c <= '\u17FF' for c in text)


def is_cjk_text(text: str) -> bool:
    """Checks if text contains Chinese Hanzi or Japanese Kana characters."""
    return any(
        ('\u4E00' <= c <= '\u9FFF') or  # CJK Unified Ideographs
        ('\u3040' <= c <= '\u309F') or  # Hiragana
        ('\u30A0' <= c <= '\u30FF')     # Katakana
        for c in text
    )


def is_thai_text(text: str) -> bool:
    """Checks if text contains Thai Unicode characters."""
    return any('\u0E00' <= c <= '\u0E7F' for c in text)


def is_lao_text(text: str) -> bool:
    """Checks if text contains Lao Unicode characters."""
    return any('\u0E80' <= c <= '\u0EFF' for c in text)


def is_myanmar_text(text: str) -> bool:
    """Checks if text contains Myanmar (Burmese) Unicode characters."""
    return any('\u1000' <= c <= '\u109F' for c in text)


def detect_text_language(text: str) -> str:
    """Detects ISO-639-1 language code from string content."""
    if not text:
        return "en"
    if is_khmer_text(text):
        return "km"
    if any('\u3040' <= c <= '\u309F' or '\u30A0' <= c <= '\u30FF' for c in text):
        return "ja"
    if any('\u4E00' <= c <= '\u9FFF' for c in text):
        return "zh"
    if any('\uAC00' <= c <= '\uD7AF' or '\u1100' <= c <= '\u11FF' for c in text):
        return "ko"
    if is_thai_text(text):
        return "th"
    if is_lao_text(text):
        return "lo"
    if is_myanmar_text(text):
        return "my"
    if any('\u0900' <= c <= '\u097F' for c in text):
        return "hi"
    if any('\u0600' <= c <= '\u06FF' for c in text):
        return "ar"
    if any('\u0400' <= c <= '\u04FF' for c in text):
        return "ru"
    if re.search(r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]', text, re.IGNORECASE):
        return "vi"
    return "en"


def tokenize_line_words(text: str) -> List[str]:
    """
    Universal multi-language word & syllable tokenizer.
    Supports Khmer (via khmernltk/clustering), Chinese & Japanese (character/kana units),
    Thai/Lao/Myanmar (syllable clusters), and spaced languages (Latin, Cyrillic, Arabic, etc.).
    Preserves embedded Latin words as full units while tokenizing unspaced scripts.
    """
    if not text:
        return []
    clean = clean_subtitle_text(text)
    if not clean:
        return []

    # 1. Khmer script
    if is_khmer_text(clean):
        if khmer_word_tokenize:
            try:
                tokens = khmer_word_tokenize(clean)
                if isinstance(tokens, list) and tokens:
                    res = [t.strip() for t in tokens if t.strip()]
                    if res:
                        return res
            except Exception:
                pass
        km_tokens = re.findall(r'[\u1780-\u17A2][\u17D2][\u1780-\u17A2][\u17B6-\u17D3]*|[\u1780-\u17D3]+|[a-zA-Z0-9_\'-]+|[^\s]', clean)
        km_tokens = [t.strip() for t in km_tokens if t.strip()]
        if km_tokens:
            return km_tokens

    # 2. Chinese & Japanese (CJK Ideographs + Kana)
    if is_cjk_text(clean):
        cjk_tokens = re.findall(r'[a-zA-Z0-9_\'-]+|[\u4e00-\u9fff]|[\u3040-\u309f]+|[\u30a0-\u30ff]+|[^\s]', clean)
        cjk_tokens = [t.strip() for t in cjk_tokens if t.strip()]
        if cjk_tokens:
            return cjk_tokens

    # 3. Thai script
    if is_thai_text(clean):
        thai_tokens = re.findall(r'[a-zA-Z0-9_\'-]+|[\u0E01-\u0E2E][\u0E30-\u0E3A\u0E47-\u0E4E]*|[\u0E2F-\u0E5B]|[^\s]', clean)
        thai_tokens = [t.strip() for t in thai_tokens if t.strip()]
        if thai_tokens:
            return thai_tokens

    # 4. Standard whitespace tokenization for spaced languages
    words = clean.split()
    return words if words else [clean]


# Common Whisper Khmer singing misrecognitions & standardizations
KHMER_SINGING_CORRECTIONS: Dict[str, str] = {
    "បេស្ដូង": "បេះដូង",    # heart
    "បេះដង": "បេះដូង",
    "ស្រាលាញ": "ស្រឡាញ់",  # love
    "ស្រលាញ់": "ស្រឡាញ់",
    "កំសត់": "កម្សត់",      # sad/sorrow
    "កំសាន្ត": "កម្សាន្ត",   # entertainment
    "សង្ខារ": "សង្សារ",     # sweetheart
    "ប្រលឹម": "ព្រលឹម",     # dawn
    "ព្រលឹង": "ព្រលឹង",     # soul
    "ដួងចន្ទ": "ដួងចន្ទ",   # moon
    "ដួងចិត្ត": "ដួងចិត្ត",   # heart/spirit
    "ទឹកភ្នែក": "ទឹកភ្នែក",  # tears
    "ស្នេហា": "ស្នេហា",     # love
}


def clean_subtitle_text(text: str) -> str:
    """Cleans subtitle and lyric cues from HTML tags, sound effects, and brackets."""
    text = html.unescape(text)
    text = re.sub(r'\[.*?\]', '', text)       # [តន្ត្រី], [music], [applause]
    text = re.sub(r'\(.*?\)', '', text)       # (music), (backing vocals)
    text = re.sub(r'>>', '', text)            # >> rolling cues
    text = re.sub(r'<.*?>', '', text)         # <c.color>, <b>, </i>
    text = re.sub(r'\{.*?\}', '', text)       # {\an8} subtitle positioning
    text = re.sub(r'\s+', ' ', text).strip()

    # Apply authentic Khmer vocal spelling standardizations
    if is_khmer_text(text):
        for wrong, right in KHMER_SINGING_CORRECTIONS.items():
            if wrong in text:
                text = text.replace(wrong, right)

    return text


def parse_lrc_file(lrc_content: str) -> List[Dict[str, Any]]:
    """
    Parses standard LRC or enhanced LRC text into structured lyric lines
    with word-level timing interpolation and Khmer tokenization.
    """
    lines = lrc_content.splitlines()
    time_regex = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{2,3}))?\]")

    raw_items = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip metadata tags like [ti:Title], [ar:Artist]
        if re.match(r"^\[[a-zA-Z]+:", line):
            continue

        match = time_regex.search(line)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            millis = match.group(3)
            fraction = float(f"0.{millis}") if millis else 0.0
            start_time = minutes * 60 + seconds + fraction

            clean_text = clean_subtitle_text(time_regex.sub("", line))
            if clean_text:
                raw_items.append((start_time, clean_text))

    raw_items.sort(key=lambda x: x[0])

    parsed_lines = []
    for i, (start_time, text) in enumerate(raw_items):
        if i + 1 < len(raw_items):
            end_time = raw_items[i + 1][0]
        else:
            end_time = start_time + 4.0

        words = tokenize_line_words(text)
        num_words = max(1, len(words))
        duration = max(0.4, end_time - start_time)
        word_dur = duration / num_words

        word_list = []
        for w_idx, w in enumerate(words):
            w_start = start_time + w_idx * word_dur
            w_end = w_start + word_dur
            word_list.append({
                "word": w,
                "start": round(w_start, 2),
                "end": round(w_end, 2)
            })

        parsed_lines.append({
            "line_id": i,
            "start": round(start_time, 2),
            "end": round(end_time, 2),
            "text": text,
            "words": word_list
        })

    return parsed_lines


def parse_subtitle_content(content: str) -> List[Dict[str, Any]]:
    """
    Intelligently parses WebVTT (.vtt), SubRip (.srt), or LRC lyrics,
    extracts cleaned text lines, applies Khmer word segmentation,
    and returns timestamped word-level karaoke data.
    """
    # Check if this is an LRC file first
    if re.search(r"\[\d{1,2}:\d{2}(?:\.\d{2,3})?\]", content):
        return parse_lrc_file(content)

    # Otherwise parse as VTT / SRT
    time_pat = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,\.](\d{2,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,\.](\d{2,3})")
    lines = content.splitlines()
    cues = []
    current_cue = None

    for line in lines:
        line = line.strip()
        m = time_pat.search(line)
        if m:
            s_h, s_m, s_s, s_ms = map(int, m.groups()[:4])
            e_h, e_m, e_s, e_ms = map(int, m.groups()[4:])
            s_ms_val = s_ms / 1000.0 if len(m.group(4)) == 3 else s_ms / 100.0
            e_ms_val = e_ms / 1000.0 if len(m.group(8)) == 3 else e_ms / 100.0
            start = s_h * 3600 + s_m * 60 + s_s + s_ms_val
            end = e_h * 3600 + e_m * 60 + e_s + e_ms_val
            current_cue = {"start": start, "end": end, "text_parts": []}
            cues.append(current_cue)
        elif current_cue and line and not line.isdigit() and not line.startswith("WEBVTT") and not line.startswith("Kind:") and not line.startswith("Language:"):
            clean = clean_subtitle_text(line)
            if clean:
                current_cue["text_parts"].append(clean)

    results = []
    line_id = 0
    for c in cues:
        dur = c["end"] - c["start"]
        if dur < 0.2:
            continue
        full_text = " ".join(c["text_parts"]).strip()
        if not full_text:
            continue
        # Avoid duplicate consecutive rolling cues
        if results and (results[-1]["text"] == full_text or full_text in results[-1]["text"]):
            continue

        words_list = tokenize_line_words(full_text)
        w_dur = max(0.05, dur / max(1, len(words_list)))

        word_data = []
        for w_idx, w in enumerate(words_list):
            word_data.append({
                "word": w,
                "start": round(c["start"] + w_idx * w_dur, 2),
                "end": round(c["start"] + (w_idx + 1) * w_dur, 2)
            })

        results.append({
            "line_id": line_id,
            "start": round(c["start"], 2),
            "end": round(c["end"], 2),
            "text": full_text,
            "words": word_data
        })
        line_id += 1

    return results


def parse_subtitle_file(file_path: str) -> List[Dict[str, Any]]:
    """Loads and parses any subtitle or lyric file (.vtt, .srt, .lrc)."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    return parse_subtitle_content(content)


def find_matching_subtitles(audio_path: str, target_lang: Optional[str] = None) -> Optional[str]:
    """
    Searches for subtitle files (.vtt, .srt, .lrc) that match an audio file.
    Intelligently ranks subtitle files matching the target language or detected song language:
    - If target_lang is specified (e.g. 'vi', 'en', 'km', 'zh'), prioritizes matching subtitles.
    - If target_lang is 'auto' or unspecified, detects the language of the song title/audio.
    - Inspects content of subtitle files to verify true language (e.g. Vietnamese text in .en.vtt).
    """
    if not audio_path:
        return None
    dir_name = os.path.dirname(os.path.abspath(audio_path))
    base_name = os.path.splitext(os.path.basename(audio_path))[0]

    title_lang = detect_text_language(base_name)
    preferred_lang = target_lang if (target_lang and target_lang != "auto") else title_lang

    search_dirs = [dir_name]
    yt_dir = os.path.join(dir_name, "youtube")
    if os.path.isdir(yt_dir):
        search_dirs.append(yt_dir)

    candidates = []
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for f in os.listdir(d):
            f_lower = f.lower()
            if not f_lower.endswith((".vtt", ".srt", ".lrc")):
                continue
            f_base = os.path.splitext(f)[0]
            if base_name in f or f_base.startswith(base_name) or base_name.startswith(f_base):
                full = os.path.join(d, f)
                priority = 0

                # Read sample to detect true language of content
                file_lang = None
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as sub_f:
                        preview = sub_f.read(1500)
                        file_lang = detect_text_language(preview)
                except Exception:
                    pass

                # Priority matching
                if preferred_lang:
                    if file_lang == preferred_lang:
                        priority += 30  # Actual content matches desired language!
                    elif f".{preferred_lang}." in f_lower or f"_{preferred_lang}." in f_lower:
                        priority += 20
                else:
                    if title_lang == "km" and file_lang == "km":
                        priority += 25
                    elif title_lang != "km" and file_lang == title_lang:
                        priority += 25

                if f_lower.endswith(".lrc"):
                    priority += 5
                elif f_lower.endswith(".vtt"):
                    priority += 4
                elif f_lower.endswith(".srt"):
                    priority += 3

                candidates.append((priority, full))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


class WhisperTranscriber:
    """Handles automatic speech-to-text with word-level timestamps and Khmer support."""

    def __init__(self, model_size: str = "base", device: str = "auto", compute_type: str = "default"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None
        self.last_detected_language = None
        self.last_detected_probability = 1.0

    def _load_model(self, progress_callback=None):
        if self.model is not None:
            return

        if progress_callback:
            progress_callback(5, "Loading Whisper AI model...")

        try:
            from faster_whisper import WhisperModel
            dev = "cpu"
            c_type = "int8"

            try:
                import torch
                if torch.cuda.is_available():
                    dev = "cuda"
                    c_type = "float16"
            except ImportError:
                pass

            cpu_threads = min(8, os.cpu_count() or 4)
            self.model = WhisperModel(self.model_size, device=dev, compute_type=c_type, cpu_threads=cpu_threads)
            if progress_callback:
                progress_callback(18, "AI model ready. Loading audio...")
        except Exception as e:
            try:
                import whisper
                self.model = whisper.load_model(self.model_size)
                if progress_callback:
                    progress_callback(18, "AI model ready. Loading audio...")
            except Exception as e2:
                raise RuntimeError(f"Could not load Whisper model: {e} / {e2}")

    def transcribe(self, audio_path: str, language: Optional[str] = None, progress_callback=None) -> List[Dict[str, Any]]:
        """
        Transcribes audio into synchronized lyric lines with word-level timestamps.
        Includes automatic Khmer language detection and tokenization with progress reporting.
        """
        self._load_model(progress_callback=progress_callback)

        # Khmer is the primary core studio focus
        if language is None or language == "":
            language = "km"
        elif language in ("auto", "None"):
            if is_khmer_text(os.path.basename(audio_path)):
                language = "km"
            else:
                language = None  # Full multilingual auto-detection

        lyrics = []
        line_counter = 0

        # Check faster-whisper vs standard whisper
        if hasattr(self.model, "transcribe") and "faster_whisper" in str(type(self.model)):
            if progress_callback:
                progress_callback(20, "Analyzing vocal tracks...")

            # Fast 1-beam greedy decoding (5x faster on CPU than beam_size=5)
            try:
                segments_gen, info = self.model.transcribe(
                    audio_path,
                    word_timestamps=True,
                    language=language,
                    beam_size=1,
                    best_of=1,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500)
                )
                dur = getattr(info, "duration", 0) or 1.0
                self.last_detected_language = getattr(info, "language", language or "en")
                self.last_detected_probability = getattr(info, "language_probability", 1.0)
                segments = []
                for s in segments_gen:
                    segments.append(s)
                    if progress_callback and dur > 0:
                        pct = min(94, int(20 + 74 * (s.end / dur)))
                        progress_callback(pct, f"Transcribing vocals ({pct}%)")
            except Exception as e:
                print(f"Faster-whisper VAD error: {e}")
                segments = []

            # If VAD produced 0 segments (common with music singing), retry with vad_filter=False
            if not segments:
                print("[Whisper AI] VAD produced 0 segments; retrying with vad_filter=False for singing vocals...")
                if progress_callback:
                    progress_callback(25, "Transcribing full audio track...")
                segments_gen, info = self.model.transcribe(
                    audio_path,
                    word_timestamps=True,
                    language=language,
                    beam_size=1,
                    best_of=1,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    vad_filter=False
                )
                dur = getattr(info, "duration", 0) or 1.0
                self.last_detected_language = getattr(info, "language", language or "en")
                self.last_detected_probability = getattr(info, "language_probability", 1.0)
                segments = []
                for s in segments_gen:
                    segments.append(s)
                    if progress_callback and dur > 0:
                        pct = min(94, int(25 + 69 * (s.end / dur)))
                        progress_callback(pct, f"Transcribing vocals ({pct}%)")

            if progress_callback:
                progress_callback(95, "Aligning word timestamps...")

            for segment in segments:
                line_text = clean_subtitle_text(segment.text)
                if not line_text:
                    continue

                words_data = []
                if segment.words:
                    for w in segment.words:
                        w_text = clean_subtitle_text(w.word)
                        if not w_text:
                            continue

                        # Apply sub-word tokenization for unspaced scripts (Khmer, CJK, Thai)
                        if is_khmer_text(w_text) or is_cjk_text(w_text) or is_thai_text(w_text):
                            real_words = tokenize_line_words(w_text)
                            if len(real_words) > 1:
                                dur = max(0.01, w.end - w.start)
                                w_dur = dur / len(real_words)
                                for i, r_word in enumerate(real_words):
                                    words_data.append({
                                        "word": r_word,
                                        "start": round(w.start + i * w_dur, 2),
                                        "end": round(w.start + (i + 1) * w_dur, 2),
                                        "probability": getattr(w, "probability", 1.0)
                                    })
                                continue

                        words_data.append({
                            "word": w_text,
                            "start": round(w.start, 2),
                            "end": round(w.end, 2),
                            "probability": getattr(w, "probability", 1.0)
                        })

                if not words_data:
                    # Fallback word interpolation with Khmer tokenization
                    raw_words = tokenize_line_words(line_text)
                    w_dur = max(0.1, (segment.end - segment.start) / max(1, len(raw_words)))
                    for idx, w in enumerate(raw_words):
                        words_data.append({
                            "word": w,
                            "start": round(segment.start + idx * w_dur, 2),
                            "end": round(segment.start + (idx + 1) * w_dur, 2)
                        })

                lyrics.append({
                    "line_id": line_counter,
                    "start": round(segment.start, 2),
                    "end": round(segment.end, 2),
                    "text": line_text,
                    "words": words_data
                })
                line_counter += 1

        else:
            # Fallback standard openai-whisper
            import whisper
            result = self.model.transcribe(audio_path, word_timestamps=True, language=language)
            self.last_detected_language = result.get("language", language or "en")
            for seg in result.get("segments", []):
                line_text = clean_subtitle_text(seg.get("text", ""))
                if not line_text:
                    continue

                words_data = []
                for w in seg.get("words", []):
                    w_text = clean_subtitle_text(w.get("word", ""))
                    if not w_text:
                        continue
                    if is_khmer_text(w_text) or is_cjk_text(w_text) or is_thai_text(w_text):
                        real_words = tokenize_line_words(w_text)
                        if len(real_words) > 1:
                            dur = max(0.01, w.get("end", 0.0) - w.get("start", 0.0))
                            w_dur = dur / len(real_words)
                            for i, r_word in enumerate(real_words):
                                words_data.append({
                                    "word": r_word,
                                    "start": round(w.get("start", 0.0) + i * w_dur, 2),
                                    "end": round(w.get("start", 0.0) + (i + 1) * w_dur, 2)
                                })
                            continue

                    words_data.append({
                        "word": w_text,
                        "start": round(w.get("start", 0.0), 2),
                        "end": round(w.get("end", 0.0), 2)
                    })

                if not words_data:
                    raw_words = tokenize_line_words(line_text)
                    w_dur = max(0.1, (seg["end"] - seg["start"]) / max(1, len(raw_words)))
                    for idx, w in enumerate(raw_words):
                        words_data.append({
                            "word": w,
                            "start": round(seg["start"] + idx * w_dur, 2),
                            "end": round(seg["start"] + (idx + 1) * w_dur, 2)
                        })

                lyrics.append({
                    "line_id": line_counter,
                    "start": round(seg.get("start", 0.0), 2),
                    "end": round(seg.get("end", 0.0), 2),
                    "text": line_text,
                    "words": words_data
                })
                line_counter += 1

        return lyrics


def get_active_lyric_frame(current_time: float, lyrics: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Returns the active lyric line, word progress, and transition alpha at a given second.
    """
    if not lyrics:
        return None

    lead_time = 0.2
    active_line = None
    next_line = None

    for idx, line in enumerate(lyrics):
        if line["start"] - lead_time <= current_time <= line["end"] + 0.5:
            active_line = line
            if idx + 1 < len(lyrics):
                next_line = lyrics[idx + 1]
            break
        elif current_time < line["start"]:
            next_line = line
            break

    if not active_line:
        return None

    active_word_index = -1
    word_progress = 0.0

    words = active_line.get("words", [])
    for w_idx, w in enumerate(words):
        if w["start"] <= current_time <= w["end"]:
            active_word_index = w_idx
            dur = max(0.05, w["end"] - w["start"])
            word_progress = (current_time - w["start"]) / dur
            break
        elif current_time > w["end"]:
            active_word_index = w_idx
            word_progress = 1.0

    fade_duration = 0.3
    alpha = 1.0
    if current_time < active_line["start"]:
        alpha = max(0.0, (current_time - (active_line["start"] - lead_time)) / lead_time)
    elif current_time > active_line["end"]:
        alpha = max(0.0, 1.0 - (current_time - active_line["end"]) / fade_duration)

    return {
        "line": active_line,
        "next_line": next_line,
        "active_word_index": active_word_index,
        "word_progress": word_progress,
        "alpha": alpha
    }
