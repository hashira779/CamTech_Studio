import os
import re
import difflib
import time
import unicodedata
import json
import logging
from typing import Dict, Any, Optional, List, Tuple

log = logging.getLogger(__name__)

# ── VIDA System Instruction ──────────────────────────────────────────────────
# Sent once per Gemini request via the dedicated system_instruction field.
# This gives the model a persistent persona identity, producing more consistent
# and higher-quality responses than embedding the persona in every user prompt.
VIDA_SYSTEM_INSTRUCTION = (
    "You are VIDA Studio's AI assistant — an expert in Khmer music, lyrics, "
    "poetry, and cultural adaptation. You speak Khmer (ភាសាខ្មែរ) and English "
    "fluently. When composing or translating Khmer lyrics, you write like a "
    "native Khmer songwriter: natural word order, everyday vocabulary, poetic "
    "but singable. You never translate word-for-word. You respect Khmer Unicode "
    "orthography including subscript consonants (ជើង \u17D2). When asked to "
    "return JSON, you return ONLY valid JSON with no markdown fences or prose."
)


LAST_GEMINI_STATUS: Optional[int] = None
LAST_GEMINI_STATUS_INFO: str = ""


def get_last_gemini_status() -> Tuple[Optional[int], str]:
    """Status of the most recent Gemini call: (None, '') on success, else (HTTP code, reason).

    The studio needs this because three failures look identical to the user — no key, quota spent,
    or a model that repeated the input — and only the last one is worth simply retrying.
    """
    return LAST_GEMINI_STATUS, LAST_GEMINI_STATUS_INFO


def call_gemini_api(prompt: str, json_mode: bool = False, timeout: int = 25,
                    total_timeout: Optional[float] = None,
                    system_instruction: Optional[str] = VIDA_SYSTEM_INSTRUCTION) -> Optional[str]:
    """Helper to query Gemini Cloud AI with auto-fallback across fast models.

    `timeout` is the budget for one model attempt. `total_timeout` is the budget for the whole
    call: without it a busy 12-line lyric request can silently consume six sequential attempts
    (the Khmer prompt alone measures ~44s per attempt) and leave the studio waiting on a request
    its own browser has already given up on.
    """
    global LAST_GEMINI_STATUS, LAST_GEMINI_STATUS_INFO
    LAST_GEMINI_STATUS = None
    LAST_GEMINI_STATUS_INFO = ""
    try:
        try:
            from backend.khmer_lyric_matcher import get_gemini_api_key
        except ImportError:
            from khmer_lyric_matcher import get_gemini_api_key
        api_key = get_gemini_api_key()
        if not api_key:
            return None
        import urllib.request
        import urllib.error
        import json
        try:
            from backend.khmer_lyric_matcher import set_last_key_error
        except ImportError:
            try:
                from khmer_lyric_matcher import set_last_key_error
            except ImportError:
                set_last_key_error = lambda x: None

        # Simplified to 3 models: latest (auto-routes to newest), a pinned stable
        # version, and a lite fallback in a separate rate bucket.
        models = [
            "gemini-flash-latest",
            "gemini-3.8-flash",
            "gemini-flash-lite-latest"
        ]
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        # System instruction gives the model a persistent persona identity,
        # producing more consistent and higher-quality responses.
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}
        if json_mode:
            payload["generationConfig"] = {"response_mime_type": "application/json"}
        data_bytes = json.dumps(payload).encode("utf-8")
        started = time.monotonic()
        consecutive_429 = 0
        for model in models:
            attempt_timeout = timeout
            if total_timeout is not None:
                left = total_timeout - (time.monotonic() - started)
                if left <= 1:
                    break
                attempt_timeout = max(1, min(timeout, left))
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            headers = {"Content-Type": "application/json", "X-goog-api-key": api_key}
            try:
                req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=attempt_timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if text:
                        set_last_key_error(None)
                        # A model that 429s and then hands the job to the next one still answered,
                        # so the rate-limit note must not survive into a successful response.
                        LAST_GEMINI_STATUS = None
                        LAST_GEMINI_STATUS_INFO = ""
                        return text
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                if e.code in (400, 401, 403):
                    try:
                        err_json = json.loads(err_body)
                        msg = err_json.get("error", {}).get("message", "")
                        if "API_KEY_INVALID" in msg or "API key not valid" in msg or "expired" in msg.lower():
                            set_last_key_error(f"Gemini API Key is invalid or expired: {msg}")
                            break
                    except Exception:
                        pass
                    set_last_key_error(f"Gemini API authentication failed (HTTP {e.code})")
                    break
                # Keep only the error enum, never the body: quota messages can name the project.
                status_name = ""
                try:
                    status_name = str(json.loads(err_body).get("error", {}).get("status", ""))
                except Exception:
                    pass
                if LAST_GEMINI_STATUS is None or e.code == 429:
                    LAST_GEMINI_STATUS = e.code
                    LAST_GEMINI_STATUS_INFO = status_name
                if e.code == 429:
                    consecutive_429 += 1
                    if consecutive_429 >= 2:
                        print(f"[Gemini] {model} rate limit (HTTP 429). Project quota exhausted; stopping model failover.")
                        break
                print(f"[Gemini] {model} refused the request (HTTP {e.code}), trying the next model")
                continue
            except Exception as e:
                if LAST_GEMINI_STATUS is None:
                    LAST_GEMINI_STATUS_INFO = type(e).__name__
                print(f"[Gemini] {model} attempt failed: {type(e).__name__}: {e}")
                continue
    except Exception:
        pass
    print("[Gemini] no model answered this request")
    return None


# ── Schema Validation ────────────────────────────────────────────────────────
# Validates Gemini JSON responses structurally before accepting them, so
# malformed AI output is caught early instead of silently falling through
# to static templates.

def _validate_lyric_sections(data: Any) -> bool:
    """Validates that Gemini-returned lyrics JSON has the expected structure."""
    if not isinstance(data, dict):
        return False
    sections = data.get("sections")
    if not isinstance(sections, list) or len(sections) == 0:
        return False
    for sec in sections:
        if not isinstance(sec, dict):
            return False
        if not isinstance(sec.get("section"), str) or not sec["section"].strip():
            return False
        lines = sec.get("lines")
        if not isinstance(lines, list) or len(lines) == 0:
            return False
        if not all(isinstance(l, str) and l.strip() for l in lines):
            return False
    return True


class LocalLLMEngine:
    """
    LocalLLMEngine integrates with llama.cpp to run highly optimized GGUF 
    local models (like SeaLLMs) on CPU RAM at blazing fast speeds.

    Includes conversation memory for iterative refinement (e.g. "make the
    chorus sadder") and weighted semantic scoring for offline mood analysis.
    """
    # Maximum number of conversation turns to keep in memory
    MAX_HISTORY_TURNS = 10

    def __init__(self):
        self.llm = None
        self.is_loaded = False
        self.has_warned = False
        # Conversation memory: allows iterative refinement across requests
        self.conversation_history: List[Dict[str, str]] = []

    def _remember(self, role: str, content: str) -> None:
        """Appends a turn to conversation memory, trimming old turns."""
        self.conversation_history.append({"role": role, "content": content})
        if len(self.conversation_history) > self.MAX_HISTORY_TURNS * 2:
            self.conversation_history = self.conversation_history[-(self.MAX_HISTORY_TURNS * 2):]

    def _build_context_prefix(self) -> str:
        """Builds a conversation context string from recent history for Gemini."""
        if not self.conversation_history:
            return ""
        lines = []
        for turn in self.conversation_history[-6:]:  # Last 3 exchanges
            prefix = "User" if turn["role"] == "user" else "VIDA"
            # Truncate long assistant responses to save tokens
            text = turn["content"]
            if turn["role"] == "assistant" and len(text) > 300:
                text = text[:300] + "..."
            lines.append(f"{prefix}: {text}")
        return "## Previous conversation:\n" + "\n".join(lines) + "\n\n"

    def clear_history(self) -> None:
        """Clears conversation memory."""
        self.conversation_history.clear()

    def load_model(self):
        if self.is_loaded:
            return
        try:
            from llama_cpp import Llama
            
            # Try multiple model paths: prefer larger, more capable models
            models_dir = os.path.join(os.path.dirname(__file__), "..", "models")
            models_dir = os.path.abspath(models_dir)
            candidate_models = [
                "Qwen2.5-7B-Instruct.Q4_K_M.gguf",
                "Gemma-3-4B-IT.Q6_K.gguf",
                "SeaLLMs-v3-7B-Chat.Q4_K_M.gguf",
                "SeaLLMs-v3-1.5B-Chat.Q4_K_M.gguf",  # Original fallback
            ]
            model_path = None
            for candidate in candidate_models:
                p = os.path.join(models_dir, candidate)
                if os.path.exists(p):
                    model_path = p
                    break

            if not model_path:
                if not self.has_warned:
                    print(f"[LLM Engine] No GGUF model found in {models_dir}. Using smart offline semantic analyzer.")
                    self.has_warned = True
                self.is_loaded = True
                return
                
            print(f"[LLM Engine] Loading 4-bit Quantized GGUF model: {os.path.basename(model_path)}")
            # n_ctx is context window, n_threads automatically uses CPU cores
            self.llm = Llama(model_path=model_path, n_ctx=4096, verbose=False)
            self.is_loaded = True
            print(f"[LLM Engine] GGUF Model loaded successfully: {os.path.basename(model_path)}")
        except ImportError:
            if not self.has_warned:
                print("[LLM Engine] Info: 'llama_cpp' not installed. Using built-in smart linguistic analyzer.")
                self.has_warned = True
            self.is_loaded = True
        except Exception as e:
            if not self.has_warned:
                print(f"[LLM Engine] Model init notice: {e}")
                self.has_warned = True
            self.is_loaded = True

    # ── Weighted Semantic Mood Scoring ────────────────────────────────────────
    # Replaces fragile binary keyword matching with weighted scoring.
    # Each mood has keywords with weights, and the highest total score wins.
    # This catches songs where a secondary mood overtakes a weak primary signal.
    _MOOD_KEYWORDS: Dict[str, Dict[str, float]] = {
        "romantic": {
            "ស្នេហា": 3.0, "ស្រឡាញ់": 3.0, "love": 2.5, "heart": 1.5, "yêu": 2.5,
            "tình": 2.0, "miss": 1.5, "បេះដូង": 2.5, "ចាំ": 1.0, "អូន": 1.5,
            "crush": 1.5, "kiss": 2.0, "forever": 1.0, "dream": 1.0, "ស្រមៃ": 1.5,
            "រាត្រី": 0.8, "ផ្កា": 1.0, "ចន្ទ": 1.2, "thương": 2.0, "nhớ": 1.8,
        },
        "melancholy": {
            "យំ": 3.0, "ឈឺ": 2.5, "sad": 2.5, "pain": 2.0, "tears": 2.0,
            "khóc": 2.5, "sầu": 2.0, "បែក": 2.0, "ព្រាត់": 2.5, "ឯកា": 2.5,
            "lonely": 2.0, "cry": 2.0, "goodbye": 1.5, "lost": 1.5, "rain": 1.0,
            "ភ្លៀង": 1.0, "ងងឹត": 1.5, "ស្លាប់": 1.5, "buồn": 2.0, "đau": 2.0,
        },
        "energetic": {
            "រាំ": 3.0, "សប្បាយ": 2.5, "dance": 2.5, "party": 2.5, "fire": 1.5,
            "bass": 2.0, "vui": 2.0, "club": 2.0, "jump": 2.0, "beat": 1.5,
            "trap": 1.5, "energy": 2.0, "tonight": 1.0, "ចង្វាក់": 2.0, "hype": 2.0,
        },
        "golden_era": {
            "យុគមាស": 4.0, "ស៊ីសាមុត": 4.0, "បុរាណ": 3.0, "vintage": 3.0,
            "retro": 2.5, "classic": 2.0, "ចំប៉ា": 2.5, "បាត់ដំបង": 2.0,
            "60s": 2.0, "vinyl": 2.0, "ស្ទឹង": 1.5, "ដងស្ទឹង": 1.5,
        },
        "heritage": {
            "អង្គរ": 3.5, "ប្រាសាទ": 3.0, "ជាតិ": 2.0, "heritage": 2.5,
            "កម្ពុជា": 2.0, "ដូនតា": 2.5, "ខ្មែរ": 1.5, "ទង់ជាតិ": 2.0,
            "មោទនភាព": 2.5, "វប្បធម៌": 2.0,
        },
    }

    _MOOD_META: Dict[str, Dict[str, str]] = {
        "romantic": {
            "mood": "Romantic & Sentimental",
            "theme": "Love & Longing (មនោសញ្ចេតនា)",
            "style": "Angkor Mandala / Sunset Glow",
        },
        "melancholy": {
            "mood": "Melancholic & Reflective",
            "theme": "Heartbreak & Solitude (ការព្រាត់ប្រាស)",
            "style": "Horizon Wave / Deep Blue Cyberpunk",
        },
        "energetic": {
            "mood": "Energetic & Uplifting",
            "theme": "High Energy Dance (ចង្វាក់រស់រវើក)",
            "style": "Trap Nation / Hyper Liquid Pulse",
        },
        "golden_era": {
            "mood": "Golden Era Nostalgic (យុគមាស)",
            "theme": "Cambodian 60s Vinyl Heritage",
            "style": "Vintage Vinyl (ស៊ីន ស៊ីសាមុត 33⅓ RPM)",
        },
        "heritage": {
            "mood": "Heritage & Patriotic",
            "theme": "Khmer National Pride (មោទនភាពជាតិ)",
            "style": "Angkor Dawn / Royal Gold Cinematic",
        },
    }

    def _score_mood(self, text: str) -> Tuple[str, float]:
        """Scores text against all mood keyword dictionaries, returns (best_mood, score)."""
        t = text.lower()
        best_mood = "default"
        best_score = 0.0
        for mood_name, keywords in self._MOOD_KEYWORDS.items():
            score = sum(weight for kw, weight in keywords.items() if kw in t)
            if score > best_score:
                best_score = score
                best_mood = mood_name
        return best_mood, best_score

    def _smart_fallback_analysis(self, text: str) -> str:
        """Weighted semantic mood analyzer for Khmer, Vietnamese, and multilingual lyrics.

        Uses scored keyword matching instead of binary checks, so mixed-mood
        lyrics (e.g. a sad love song) are classified by the dominant signal.
        """
        has_khmer = any(0x1780 <= ord(c) <= 0x17FF for c in text)

        best_mood, score = self._score_mood(text)

        if score >= 1.5 and best_mood in self._MOOD_META:
            meta = self._MOOD_META[best_mood]
            mood = meta["mood"]
            themes = [meta["theme"]]
            style_rec = meta["style"]
        else:
            mood = "Melodic & Emotional"
            themes = ["Poetic Narrative & Musical Expression"]
            style_rec = "Fluid Wave (Neon Glow)"

        lang_label = "Khmer (ភាសាខ្មែរ)" if has_khmer else "Multilingual"
        confidence = f" (confidence: {min(score / 6.0, 1.0):.0%})" if score > 0 else ""

        return (
            f"🎵 **Language**: {lang_label}\n"
            f"✨ **Mood**: {mood}{confidence}\n"
            f"📝 **Themes**: {', '.join(themes)}\n"
            f"🎨 **Recommended Visual Style**: {style_rec}"
        )

    def generate_khmer_lyrics(self, prompt: str = "", genre: str = "romantic", bpm: int = 85) -> Dict[str, Any]:
        """
        Generates structured, poetic Khmer lyrics with rhyming verse patterns,
        complete with Verse 1, Verse 2, Chorus/Hook, and Outro, along with
        ready-to-sync timestamped LRC format.
        """
        if not self.is_loaded:
            self.load_model()

        # Check genre and select authentic poetic templates
        g = (genre or "romantic").lower()
        p_lower = prompt.lower() if prompt else ""

        if any(w in p_lower for w in ["យុគមាស", "ស៊ីសាមុត", "បុរាណ", "vintage", "retro", "60s", "classic", "ចំប៉ា", "បាត់ដំបង"]):
            g = "golden_era"
        elif any(w in p_lower for w in ["យំ", "ឈឺ", "sad", "pain", "tears", "ព្រាត់", "បែក", "ឯកា", "ស្លាប់"]):
            g = "melancholy"
        elif any(w in p_lower for w in ["រាំ", "សប្បាយ", "dance", "party", "ចូលឆ្នាំ", "ក្បាច់", "រាំវង់"]):
            g = "romvong"
        elif any(w in p_lower for w in ["remix", "trap", "bass", "pop", "modern", "យុវវ័យ", "ទាន់សម័យ"]):
            g = "modern_pop"
        elif any(w in p_lower for w in ["អង្គរ", "ប្រាសាទ", "ជាតិ", "heritage", "កម្ពុជា", "ដូនតា"]):
            g = "heritage"

        # Genre presets with authentic poetic verses & rhyming meters
        presets = {
            "romantic": {
                "title": "រាត្រីស្រមៃស្នេហ៍ (Dreaming of You)",
                "genre_name": "Romantic Ballad (មនោសញ្ចេតនាផ្អែមល្ហែម)",
                "tempo_bpm": 78,
                "sections": [
                    {
                        "section": "វគ្គទី១ (Verse 1)",
                        "lines": [
                            "សន្សើមធ្លាក់ស្រាលក្នុងរាត្រីស្ងប់ស្ងាត់",
                            "ដួងចន្ទរះកាត់បំភ្លឺដួងចិត្ត",
                            "នឹកឃើញរូបអូនជាគូជីវិត",
                            "ស្នេហ៍ពិតឥតកែប្រែក្នុងដួងហរទ័យ។"
                        ]
                    },
                    {
                        "section": "វគ្គទី២ (Verse 2)",
                        "lines": [
                            "ខ្យល់បក់រំភើយនាំក្លិនផ្ការំដួល",
                            "ចិត្តបងរំជួលនឹកគ្រាជួបស្រី",
                            "ស្នាមញញឹមអូនស្រស់ដូចគំនូរថ្មី",
                            "បងសច្ចារាល់ថ្ងៃស្មោះមួយនឹងអូន។"
                        ]
                    },
                    {
                        "section": "បន្ទរ (Chorus)",
                        "lines": [
                            "ឱដួងចន្ទថ្លាជួយធ្វើសាក្សី",
                            "បងស្រឡាញ់ស្រីអស់ពីបេះដូង",
                            "ទោះមេឃរលំភ្នំរលាយក៏ដោយ",
                            "បងមិនលះបង់អូនចោលឡើយណាជីវា។"
                        ]
                    },
                    {
                        "section": "វគ្គបញ្ចប់ (Outro)",
                        "lines": [
                            "ក្ដីស្រឡាញ់បងផ្ញើតាមខ្យល់រាត្រី",
                            "ថ្នាក់ថ្នមរូបស្រីរហូតអស់ដង្ហើម។"
                        ]
                    }
                ]
            },
            "golden_era": {
                "title": "ចំប៉ាបាត់ដំបង (Battambang Jasmine)",
                "genre_name": "1960s Golden Era Vinyl (យុគមាស ឆ្នាំ៦០)",
                "tempo_bpm": 82,
                "sections": [
                    {
                        "section": "វគ្គទី១ (Verse 1)",
                        "lines": [
                            "រសៀលគងព្រៃដីក្រហមបាត់ដំបង",
                            "ជំនោររលកដងស្ទឹងសង្កែ",
                            "ក្រឡេកឃើញស្រីកំពូលស្នេហ៍",
                            "សម្រស់មាសមេដក់ជាប់អារម្មណ៍។"
                        ]
                    },
                    {
                        "section": "វគ្គទី២ (Verse 2)",
                        "lines": [
                            "ផ្កាចំប៉ារីកក្រអូបសព្វសព្វទិស",
                            "ដូចចិត្តពិសិដ្ឋដែលស្មោះភក្តី",
                            "រង់ចាំជួបអូនរាល់វេលាថ្មី",
                            "មិនភ្លេចសម្ដីដែលធ្លាប់សន្យា។"
                        ]
                    },
                    {
                        "section": "បន្ទរ (Chorus)",
                        "lines": [
                            "ឱស្ទឹងសង្កែអើយជួយឮបណ្ដាំ",
                            "ចិត្តបងនៅចាំតែស្រីគ្រប់គ្រា",
                            "ទោះបីជួបទុក្ខឬក្ដីវេទនា",
                            "បងនៅតែស៊ូជួបអូនរៀងរហូត។"
                        ]
                    },
                    {
                        "section": "វគ្គបញ្ចប់ (Outro)",
                        "lines": [
                            "ចំប៉ាបាត់ដំបងក្រអូបមិនរសាយ",
                            "ដូចស្នេហ៍បងកាយថ្វាយជូនតែអូន។"
                        ]
                    }
                ]
            },
            "melancholy": {
                "title": "ទឹកភ្នែកក្រោមតំណក់ភ្លៀង (Tears in the Rain)",
                "genre_name": "Melancholy & Heartbreak (កម្សត់ និងការព្រាត់ប្រាស)",
                "tempo_bpm": 68,
                "sections": [
                    {
                        "section": "វគ្គទី១ (Verse 1)",
                        "lines": [
                            "មេឃភ្លៀងស្រក់ស្រពោនបេះដូង",
                            "ឈរឯកាក្នុងបន្ទប់ងងឹតសូន្យ",
                            "ឃើញរូបថតចាស់ដែលធ្លាប់មានអូន",
                            "ឥឡូវបាត់បង់សល់តែក្ដីឈឺចាប់។"
                        ]
                    },
                    {
                        "section": "វគ្គទី២ (Verse 2)",
                        "lines": [
                            "ពាក្យសន្យាអូនថានឹងមិនប្រែប្រួល",
                            "ហេតុអ្វីប្រែស្រួលដើរចេញគ្មានស្ដាយ",
                            "ទុកឱ្យបងយំស្ទើរធ្លាយបេះដូងកាយ",
                            "ស្រមោលអូនឆ្ងាយលែងវិលត្រឡប់។"
                        ]
                    },
                    {
                        "section": "បន្ទរ (Chorus)",
                        "lines": [
                            "ទឹកភ្នែកហូរច្របល់តំណក់ទឹកភ្លៀង",
                            "បន្លឺសំនៀងស្រែកហៅឈ្មោះស្រី",
                            "បងដឹងច្បាស់ហើយគ្មានអូនជាថ្មី",
                            "ជីវិតពេលនេះប្រៀបដូចរាត្រីគ្មានផ្កាយ។"
                        ]
                    },
                    {
                        "section": "វគ្គបញ្ចប់ (Outro)",
                        "lines": [
                            "លាហើយស្នេហាដែលធ្លាប់ស្រស់បំព្រង",
                            "សូមអូនសុខចុះជាមួយគេថ្មី។"
                        ]
                    }
                ]
            },
            "romvong": {
                "title": "រាំវង់ស្រុកស្រែចូលឆ្នាំថ្មី (Khmer New Year Dance)",
                "genre_name": "Festive Romvong Folk (រាំវង់ប្រពៃណីចូលឆ្នាំ)",
                "tempo_bpm": 105,
                "sections": [
                    {
                        "section": "វគ្គទី១ (Verse 1)",
                        "lines": [
                            "ស្គរដៃបន្លឺតាក់ទឹងៗសប្បាយ",
                            "បងប្អូនជិតឆ្ងាយជួបជុំវត្តអារាម",
                            "កញ្ញាប្រិមប្រិយស្លៀកពាក់ស្រស់ស្អាត",
                            "ចូលរាំជិតគ្នាបង្កើតមេត្រី។"
                        ]
                    },
                    {
                        "section": "វគ្គទី២ (Verse 2)",
                        "lines": [
                            "រាំវង់រាំក្បាច់លេងល្បែងប្រជាប្រិយ",
                            "បោះឈូងលាក់កន្សែងសប្បាយក្រៃលែង",
                            "ញញឹមរកគ្នាឥតមានចង្អៀត",
                            "ចូលឆ្នាំថ្មីមកដល់ពោរពេញសិរី។"
                        ]
                    },
                    {
                        "section": "បន្ទរ (Chorus)",
                        "lines": [
                            "តោះរាំ! រាំវង់ចូលឆ្នាំខ្មែរយើង",
                            "សប្បាយក្អាកក្អាយទូទាំងនគរ",
                            "ជូនពរជ័យសិរីបវរ",
                            "រកស៊ីមានបានសុខសាន្តទាំងអស់គ្នា!"
                        ]
                    },
                    {
                        "section": "វគ្គបញ្ចប់ (Outro)",
                        "lines": [
                            "សប្បាយចូលឆ្នាំថ្មីប្រពៃណីខ្មែរ",
                            "រាំវង់មិនណាយរហូតទល់ភ្លឺ!"
                        ]
                    }
                ]
            },
            "modern_pop": {
                "title": "ចង្វាក់បេះដូង ២០២៦ (Cyber Heartbeat)",
                "genre_name": "Modern Khmer Pop & Trap (តន្ត្រីយុវវ័យ ២០២៦)",
                "tempo_bpm": 128,
                "sections": [
                    {
                        "section": "វគ្គទី១ (Verse 1)",
                        "lines": [
                            "ពន្លឺនេអុងចាំងផ្លេកពេញរាត្រី",
                            "Bass បុកកក្រើកដាស់អារម្មណ៍ថ្មី",
                            "ឃើញកែវភ្នែកអូនសម្លឹងចំកណ្ដាល",
                            "ធ្វើឱ្យបេះដូងបងលោតខុសចង្វាក់។"
                        ]
                    },
                    {
                        "section": "វគ្គទី២ (Verse 2)",
                        "lines": [
                            "Beat drops ទាញយកអារម្មណ៍ឱ្យហោះ",
                            "មិនខ្វល់រឿងអ្វីទាំងអស់ត្រឹមមានអូនក្បែរ",
                            "ដៃកាន់ដៃយើងរាំកាត់រាត្រី",
                            "Energy ពេញលេញជាមួយតន្ត្រីសម័យ។"
                        ]
                    },
                    {
                        "section": "បន្ទរ (Chorus)",
                        "lines": [
                            "This is our night គ្មានថ្ងៃបំភ្លេច",
                            "ចង្វាក់បេះដូងលោតតាមសាច់ភ្លេង",
                            "ក្ដីស្រឡាញ់យើងហោះឡើងខ្ពស់",
                            "Together we shine like neon stars!"
                        ]
                    },
                    {
                        "section": "វគ្គបញ្ចប់ (Outro)",
                        "lines": [
                            "Feel the bass, feel the love tonight",
                            "យើងនៅជាមួយគ្នាជារៀងរហូត។"
                        ]
                    }
                ]
            },
            "heritage": {
                "title": "មោទនភាពដួងព្រលឹងអង្គរ (Spirit of Angkor)",
                "genre_name": "Khmer Heritage Majesty (មោទនភាពប្រាសាទអង្គរ)",
                "tempo_bpm": 75,
                "sections": [
                    {
                        "section": "វគ្គទី១ (Verse 1)",
                        "lines": [
                            "កំពូលប្រាសាទសិលាថ្មថ្លៃ",
                            "អង្គរវត្តអស្ចារ្យកប់ក្នុងប្រវត្តិសាស្ត្រ",
                            "ស្នាដៃបុព្វបុរសដូនតាខ្មែរ",
                            "កេរដំណែលពិសិដ្ឋលើសកលលោកា។"
                        ]
                    },
                    {
                        "section": "វគ្គទី២ (Verse 2)",
                        "lines": [
                            "ក្បូរក្បាច់រចនាអប្សរារាំរស់រវើក",
                            "ពន្លឺព្រះអាទិត្យរះផុតកំពូលប្រាសាទ",
                            "ដួងព្រលឹងខ្មែររឹងមាំដូចថ្មភ្នំ",
                            "រក្សាការពារទង់ជាតិកម្ពុជា។"
                        ]
                    },
                    {
                        "section": "បន្ទរ (Chorus)",
                        "lines": [
                            "ឱកម្ពុជាមាតុភូមិជាទីស្នេហា",
                            "កូនខ្មែររួមចិត្តសាមគ្គីគ្នា",
                            "លើកស្ទួយវប្បធម៌ដូនតាខ្មែរយើង",
                            "ឱ្យរុងរឿងចែងចាំងរៀងរហូតតទៅ!"
                        ]
                    },
                    {
                        "section": "វគ្គបញ្ចប់ (Outro)",
                        "lines": [
                            "មោទនភាពជាតិខ្មែរនៅលើផែនដី",
                            "ពូជពង្សអង្គរមិនសាបសូន្យឡើយ។"
                        ]
                    }
                ]
            }
        }

        chosen = None

        # 1. ⚡ Gemini Cloud AI Dynamic Lyric Composer (Fast 1-2s, 100% authentic poetic structure)
        try:
            import json
            gem_prompt = (
                f"You are a master Cambodian songwriter and poet. Compose an authentic, structured, poetic Khmer song.\n"
                f"Theme/Prompt: {prompt or genre}\n"
                f"Genre: {g} ({bpm or 85} BPM)\n"
                f"Requirements:\n"
                f"1. Return ONLY valid JSON in this exact schema:\n"
                f"{{\n"
                f'  "title": "Song Title in Khmer",\n'
                f'  "sections": [\n'
                f'    {{"section": "វគ្គទី១ (Verse 1)", "lines": ["line 1", "line 2", "line 3", "line 4"]}},\n'
                f'    {{"section": "វគ្គទី២ (Verse 2)", "lines": ["line 1", "line 2", "line 3", "line 4"]}},\n'
                f'    {{"section": "បន្ទរ (Chorus)", "lines": ["line 1", "line 2", "line 3", "line 4"]}},\n'
                f'    {{"section": "វគ្គបញ្ចប់ (Outro)", "lines": ["line 1", "line 2"]}}\n'
                f"  ]\n"
                f"}}"
            )
            gem_raw = call_gemini_api(gem_prompt, json_mode=True, timeout=10)
            if gem_raw:
                parsed = json.loads(gem_raw)
                # Schema validation: reject malformed AI output early instead
                # of silently falling through to static templates.
                if _validate_lyric_sections(parsed):
                    chosen = {
                        "title": parsed.get("title", f"បទចម្រៀងខ្មែរ: {genre.capitalize()}"),
                        "genre_name": f"{genre.capitalize()} (Gemini Cloud AI)",
                        "tempo_bpm": bpm or 85,
                        "sections": parsed["sections"],
                        "model_used": "Gemini Flash (Google Cloud AI)"
                    }
                else:
                    log.warning("[Gemini Lyric Composer] Returned JSON failed schema validation, using preset")
        except Exception as gem_e:
            print(f"[Gemini Lyric Composer] Notice: {gem_e}")

        if not chosen and self.llm is not None:
            llm_prompt = (
                f"Write a short, beautiful Khmer song about: {prompt}. "
                f"Genre: {g}. "
                f"Format it with exactly [Verse 1], [Verse 2], [Chorus], and [Outro]."
                f"\n\nSong Lyrics:\n"
            )
            try:
                out = self.llm(llm_prompt, max_tokens=300, temperature=0.8, stop=["\n\n\n"])
                generated_text = out['choices'][0]['text'].strip()
                
                # Parse LLM output into sections
                sections = []
                current_section = {"section": "វគ្គទី១ (Verse 1)", "lines": []}
                for line in generated_text.splitlines():
                    line = line.strip()
                    if not line: continue
                    if line.startswith("[") and line.endswith("]"):
                        if current_section["lines"]:
                            sections.append(current_section)
                        current_section = {"section": line.strip("[]"), "lines": []}
                    else:
                        current_section["lines"].append(line)
                if current_section["lines"]:
                    sections.append(current_section)
                    
                if sections:
                    chosen = {
                        "title": f"AI Composed: {prompt[:15]}...",
                        "genre_name": f"AI {genre.capitalize()}",
                        "tempo_bpm": bpm or 85,
                        "sections": sections
                    }
            except Exception as e:
                print(f"Dynamic LLM failure: {e}")
                
        if not chosen:
            chosen = presets.get(g, presets["romantic"])

        # Format plain text with section markers
        full_text_parts = [f"🎵 {chosen['title']}", f"Style: {chosen['genre_name']}\n"]
        all_lines = []
        for s in chosen["sections"]:
            full_text_parts.append(f"[{s['section']}]")
            for line in s["lines"]:
                full_text_parts.append(line)
                all_lines.append(line)
            full_text_parts.append("")

        lyrics_text = "\n".join(full_text_parts).strip()

        # Build synchronized LRC file with smooth musical pacing
        lrc_lines = [
            f"[ti:{chosen['title']}]",
            f"[ar:VIDA Khmer AI Composer]",
            f"[al:{chosen['genre_name']}]",
            f"[by:VIDA Studio Pro 2026]"
        ]

        current_sec = 6.0  # Lead intro time
        structured_lyrics_data = []

        from backend.lyric_engine import tokenize_line_words, normalize_khmer_orthography

        for line_idx, line in enumerate(all_lines):
            dur = max(2.8, len(line) * 0.12)
            m = int(current_sec // 60)
            s_rem = current_sec % 60
            lrc_lines.append(f"[{m:02d}:{s_rem:05.2f}]{line}")

            # Tokenize words for word-level karaoke sync
            norm_line = normalize_khmer_orthography(line)
            tokens = tokenize_line_words(norm_line)
            w_dur = dur / max(1, len(tokens))

            words_data = []
            for w_i, tok in enumerate(tokens):
                words_data.append({
                    "word": tok,
                    "start": round(current_sec + w_i * w_dur, 2),
                    "end": round(current_sec + (w_i + 1) * w_dur, 2)
                })

            structured_lyrics_data.append({
                "line_id": line_idx,
                "start": round(current_sec, 2),
                "end": round(current_sec + dur, 2),
                "text": norm_line,
                "words": words_data
            })

            current_sec += dur + 0.8  # Slight pause between vocal lines

        lrc_content = "\n".join(lrc_lines)

        return {
            "status": "success",
            "title": chosen["title"],
            "genre": chosen["genre_name"],
            "bpm": chosen["tempo_bpm"],
            "lyrics_text": lyrics_text,
            "lrc_content": lrc_content,
            "lyrics_data": structured_lyrics_data,
            "count": len(structured_lyrics_data),
            "model_used": "VIDA Khmer Poetic AI Lyric Engine"
        }

    def polish_khmer_lyrics(self, raw_lyrics: str) -> Dict[str, Any]:
        """Fixes spelling, broken subscripts, and normalizes Khmer lyrics."""
        # 1. ⚡ Gemini Cloud AI Polish (instant & linguistically perfect)
        try:
            gem_prompt = (
                "You are an expert Khmer linguist. Fix any spelling mistakes, typos, broken subscripts, "
                "and incorrect diacritics in these Khmer lyrics line by line. "
                "Maintain identical line breaks and original meaning. "
                "Return ONLY the polished Khmer lyrics without introductory notes or markdown fences:\n\n"
                f"{raw_lyrics}"
            )
            gem_res = call_gemini_api(gem_prompt, json_mode=False, timeout=8)
            if gem_res:
                lines = [l.strip() for l in gem_res.splitlines() if l.strip() and not l.strip().startswith("```")]
                return {
                    "status": "success",
                    "polished_text": "\n".join(lines),
                    "corrections_made": len(lines),
                    "model_used": "Gemini 3.1 Flash"
                }
        except Exception as gem_e:
            print(f"[Gemini Polish] Notice: {gem_e}")

        from backend.lyric_engine import normalize_khmer_orthography
        lines = raw_lyrics.splitlines()
        fixed = []
        corrections_count = 0
        for l in lines:
            c = normalize_khmer_orthography(l.strip())
            if c != l.strip():
                corrections_count += 1
            if c:
                fixed.append(c)

        return {
            "status": "success",
            "polished_text": "\n".join(fixed),
            "corrections_made": corrections_count,
            "model_used": "Offline Rule-based"
        }

    def auto_correct_transcription(self, lyrics_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enterprise-scale Auto-Correction Pipeline.
        Takes Whisper ASR structured output and passes the text through Gemini AI or LLM to fix
        phonetic and spelling errors contextually, without altering timestamps.
        """
        if not lyrics_data:
            return lyrics_data

        sample_text = " ".join(str(l.get("text", "")) for l in lyrics_data[:10])
        has_khmer = any(0x1780 <= ord(c) <= 0x17FF for c in sample_text)

        # 1. ⚡ Gemini Cloud AI Fast-Path (1-2s, 100% accurate spelling)
        try:
            import json
            sample_input = [{"line_id": i, "text": l.get("text", "")} for i, l in enumerate(lyrics_data)]
            if has_khmer:
                role_prompt = "You are an expert Khmer linguist. Correct any phonetic spelling mistakes, typos, and missing subscript/diacritic errors in these Khmer singing lyrics while keeping identical line count and meaning."
            else:
                role_prompt = "You are an expert lyric editor. Clean up minor typos or phonetic misspellings in these singing lyrics while keeping the exact authentic language, line count, and meaning unchanged."

            gem_prompt = (
                f"{role_prompt}\n"
                "Return ONLY a JSON array with schema: [{\"line_id\": 0, \"text\": \"corrected text\"}]\n\n"
                f"Input:\n{json.dumps(sample_input, ensure_ascii=False)}"
            )
            gem_res = call_gemini_api(gem_prompt, json_mode=True, timeout=25)
            if gem_res:
                corrected_list = json.loads(gem_res)
                corrected_dict = {
                    item.get("line_id"): item.get("text")
                    for item in corrected_list
                    if item.get("line_id") is not None and item.get("text")
                }
                for i, line_data in enumerate(lyrics_data):
                    if i in corrected_dict and corrected_dict[i]:
                        lyrics_data[i]["text"] = corrected_dict[i]
                        lyrics_data[i]["words"] = []
                print(f"[Gemini Auto-Fix] ✅ Successfully corrected {len(corrected_dict)} lyric lines via Gemini AI!")
                return lyrics_data
        except Exception as gem_e:
            print(f"[Gemini Auto-Fix] Notice: {gem_e}. Falling back to local pipeline.")

        # Guard: If non-Khmer (e.g. Vietnamese, English), DO NOT load the Khmer GGUF model into CPU RAM!
        if not has_khmer:
            return lyrics_data

        # For Khmer, apply instant regex dictionary normalization first
        from backend.lyric_engine import normalize_khmer_orthography
        for idx, line in enumerate(lyrics_data):
            lyrics_data[idx]['text'] = normalize_khmer_orthography(line.get('text', ''))
        return lyrics_data

    def analyze_text(self, text: str) -> Dict[str, Any]:
        """Analyzes text or handles lyric composing requests in any language."""
        if not self.is_loaded:
            self.load_model()

        t_lower = text.lower()
        # Detect if user asks to make / compose lyrics
        lyric_keywords = [
            "សរសេរទំនុកច្រៀង", "តែងទំនុកច្រៀង", "តែងចម្រៀង", "សរសេរចម្រៀង", "កំណាព្យ", "កាព្យ",
            "make lyrics", "write lyrics", "compose lyrics", "create lyrics", "khmer lyrics",
            "បទចម្រៀង", "តែង", "lyrics for", "song about"
        ]
        if any(k in t_lower for k in lyric_keywords):
            gen_res = self.generate_khmer_lyrics(prompt=text)
            return {
                "status": "success",
                "analysis": (
                    f"✨ **AI Composed Khmer Song**: {gen_res['title']}\n"
                    f"🎭 **Genre**: {gen_res['genre']} ({gen_res['bpm']} BPM)\n\n"
                    f"{gen_res['lyrics_text']}"
                ),
                "lyrics_data": gen_res.get("lyrics_data"),
                "lrc_content": gen_res.get("lrc_content"),
                "text": text,
                "model_used": gen_res["model_used"]
            }

        # 1. ⚡ Gemini Cloud AI Fast-Path for chat & linguistic analysis (1-2s)
        #    Conversation context is prepended so users can iteratively refine.
        try:
            context = self._build_context_prefix()
            gem_prompt = (
                f"{context}"
                "Provide a clear, helpful, expert answer in the language requested (Khmer or English). "
                "Keep formatting clean with bullet points and bold headers.\n\n"
                f"User request: {text}"
            )
            self._remember("user", text)
            gem_res = call_gemini_api(gem_prompt, json_mode=False, timeout=10)
            if gem_res:
                self._remember("assistant", gem_res)
                return {
                    "status": "success",
                    "analysis": gem_res,
                    "text": text,
                    "model_used": "Gemini Flash (Google Cloud AI)"
                }
        except Exception as gem_e:
            print(f"[Gemini Chat] Notice: {gem_e}. Falling back to local analyzer.")

        if self.llm is None:
            return {
                "status": "success",
                "analysis": self._smart_fallback_analysis(text),
                "text": text,
                "model_used": "Smart Linguistic Analyzer (Offline Fallback)"
            }

        prompt = f"Analyze the following lyrics or text for mood, sentiment, musical theme, and meaning:\n\n{text}\n\nAnalysis:"

        try:
            output = self.llm(prompt, max_tokens=150, temperature=0.7, stop=["\n\n"])
            generated = output['choices'][0]['text'].strip()
            return {
                "status": "success",
                "analysis": generated,
                "text": text,
                "model_used": "SeaLLMs-v3-1.5B-Chat (4-bit GGUF)"
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def analyze_khmer_text(self, text: str) -> Dict[str, Any]:
        return self.analyze_text(text)

    def translate_text(self, text: str, target_lang: str = "Khmer") -> str:
        """Translates text between languages."""
        if not self.is_loaded:
            self.load_model()
        if self.llm is None:
            return "[Translation Failed - No Model]"

        prompt = f"Translate the following text to {target_lang}:\n\n{text}\n\nTranslation:"
        try:
            output = self.llm(prompt, max_tokens=100, temperature=0.1, stop=["\n\n"])
            return output['choices'][0]['text'].strip()
        except Exception as e:
            return f"Error: {e}"

    def translate_to_khmer(self, english_text: str) -> str:
        return self.translate_text(english_text, target_lang="Khmer")

    @staticmethod
    def _detect_source_language(texts: List[str]) -> str:
        """Auto-detects the dominant source language from a list of lyric texts."""
        sample = " ".join(texts[:30])
        if not sample.strip():
            return "Unknown"

        def _share(pred):
            letters = [c for c in sample if c.isalpha()]
            if not letters:
                return 0.0
            return sum(1 for c in letters if pred(c)) / len(letters)

        if _share(lambda c: '\u4E00' <= c <= '\u9FFF') >= 0.25:
            return "Chinese"
        if _share(lambda c: '\u3040' <= c <= '\u309F' or '\u30A0' <= c <= '\u30FF') >= 0.10:
            return "Japanese"
        if _share(lambda c: '\uAC00' <= c <= '\uD7AF' or '\u1100' <= c <= '\u11FF') >= 0.20:
            return "Korean"
        if _share(lambda c: '\u0E00' <= c <= '\u0E7F') >= 0.25:
            return "Thai"
        if _share(lambda c: '\u0E80' <= c <= '\u0EFF') >= 0.25:
            return "Lao"
        if _share(lambda c: '\u1000' <= c <= '\u109F') >= 0.25:
            return "Myanmar"
        if _share(lambda c: '\u1780' <= c <= '\u17FF') >= 0.25:
            return "Khmer"
        # Vietnamese: Latin script with significant diacritics
        vi_re = re.compile(
            r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]',
            re.IGNORECASE
        )
        vi_marks = len(vi_re.findall(sample))
        latin_letters = sum(1 for c in sample if c.isalpha() and 'a' <= c.lower() <= 'z')
        if latin_letters and vi_marks >= 2 and (vi_marks / latin_letters) >= 0.06:
            return "Vietnamese"
        return "English"

    # A real 12-line Vietnamese -> Khmer batch measures 43.8s for one model attempt with the full
    # adaptation brief in the prompt. So: 60s per attempt, and a hard ceiling for the whole call —
    # the fallback list is six models long and without a ceiling one request can silently burn
    # six attempts and outrun the browser's own timeout.
    KHMER_ATTEMPT_TIMEOUT_S = 60
    KHMER_DRAFT_TIMEOUT_S = 150
    KHMER_POLISH_TIMEOUT_S = 150

    @staticmethod
    def _build_khmer_translation_prompt(
        source_lang: str,
        payload_str: str,
        song_title: str = "",
        artist: str = ""
    ) -> str:
        """Builds the culturally-adapted Khmer lyric prompt.

        The brief the model has to follow is a meaning-first song adaptation, not a
        translation: read the feeling, drop the source sentence shape, say it the way Khmer
        lyrics are actually written, then back-check it aloud. Every rule and example pair
        below is asserted by tests/test_khmer_translation_prompt.py, because a single word-for-word
        line is what makes native listeners say "this sounds like machine translation".
        """
        return (
            "You are an award-winning Khmer song lyricist. You are NOT translating words, you are "
            "re-singing a foreign song in Khmer (ភាសាខ្មែរ) so that Khmer listeners feel it "
            "immediately and can sing along.\n\n"

            "## HOW TO WORK — MEANING FIRST, NEVER LETTER FOR LETTER:\n"
            "STEP 1 — GRASP THE MEANING: for each line, quietly answer \"what does the singer really "
            "say and feel here?\" before choosing a single Khmer word.\n"
            "STEP 2 — DROP THE SOURCE SENTENCE: forget the {src} word order and grammar. Never carry "
            "the shape of the foreign sentence into Khmer.\n"
            "STEP 3 — SAY IT IN KHMER: write the line the way a Khmer lyricist would write it — "
            "everyday words, natural Khmer word order, Khmer images and idioms.\n"
            "STEP 4 — BACK-CHECK ALOUD: read your line out loud. If a native speaker would have to "
            "pause and re-read it, it is wrong: rewrite it until it lands in one hearing, while "
            "still carrying the STEP 1 meaning.\n\n"

            "## CRITICAL RULES:\n\n"
            "1. **DO NOT translate word-by-word (កុំបកប្រែពាក្យម៉ាត់ៗ)**\n"
            "   - ❌ 'I can't stop loving you' → 'ខ្ញុំមិនអាចបញ្ឈប់ការស្រឡាញ់អ្នក'\n"
            "   - ✅ 'I can't stop loving you' → 'បេះដូងនេះមិនធ្លាប់ភ្លេចអូនសោះ'\n\n"
            "2. **Must sound like natural Khmer (ត្រូវតែស្ដាប់ជាខ្មែរធម្មជាតិ)**\n"
            "   - Use Khmer poetic expressions and idioms where appropriate\n"
            "   - The translation should feel like it was originally written in Khmer\n"
            "   - A Khmer listener must understand it immediately, without confusion\n\n"
            "3. **Preserve the emotion and meaning (រក្សាអារម្មណ៍ និងអត្ថន័យ)**\n"
            "   - Keep the original song's emotional tone (sad, happy, romantic, energetic)\n"
            "   - The core message must remain the same — adapt the words, not the feeling\n"
            "   - Adapt cultural references to Khmer equivalents when needed\n"
            "   - Never add an idea that is not in the original line, never drop its idea away\n\n"
            "4. **Use everyday Khmer vocabulary (ប្រើពាក្យខ្មែរដែលប្រើប្រចាំថ្ងៃ)**\n"
            "   - Avoid overly formal or literary Khmer that sounds unnatural\n"
            "   - Avoid Pali/Sanskrit heavy words unless they are commonly used\n"
            "   - Use words that ordinary Khmer speakers would easily understand\n\n"
            "5. **Match the rhythm and flow (ឱ្យត្រូវនឹងចង្វាក់បទ)**\n"
            "   - Keep the line close to the length of the source line so it still fits the melody\n"
            "   - Stay short enough to sing in one breath: a Khmer line above roughly 24 sung units "
            "(base consonants) is longer than any real Khmer lyric line and will not fit the cue\n"
            "   - Prefer two short Khmer clauses over one long stacked noun phrase — a sung line "
            "has to fit in one breath\n"
            "   - The Khmer text must flow smoothly when read aloud or sung along\n\n"
            "6. **Khmer script only in the output (សរសេរអក្សរខ្មែរប៉ុណ្ណោះ)**\n"
            "   - Never leave Thai, Lao, Myanmar, Vietnamese or Chinese characters inside a translated line\n"
            "   - Never romanise or transliterate a source word into Khmer letters just because "
            "no obvious word comes to mind — that is word-for-word thinking\n"
            "   - ❌ 'ปล่อយវាទៅ' (Thai characters slipped in) → ✅ 'លែងវាទៅ'\n\n"
            "7. **Pick one voice and keep it (រក្សាបង/អូនឱ្យស៊ីគ្នាទាំងបទ)**\n"
            "   - Choose the pronoun pair that fits the song (បង/អូន for romance, មិត្ត/អ្នក for "
            "friendship, ខ្ញុំ/អ្នក only when the song is truly neutral) and use it consistently "
            "in every line of this song\n"
            "   - Never switch register mid-song, and never mix អ្នក with អូន for the same person\n\n"
            "8. **One line in, one line out (មួយបន្ទាត់ ចូល មួយបន្ទាត់ ចេញ)**\n"
            "   - Keep every line independent: never merge two lines, never split one line into two\n"
            "   - Chorus repeats, hooks and 'oh/la la' sounds stay as repeats, they are not dropped\n\n"

            "## EXAMPLES (word-for-word ❌ versus natural Khmer ✅):\n\n"
            "English → Khmer\n"
            "  'You are the sunshine of my life'\n"
            "    ❌ 'អ្នកជាពន្លឺថ្ងៃនៃជីវិតរបស់ខ្ញុំ'   ✅ 'អូនជាពន្លឺបំភ្លឺបេះដូងបង'\n"
            "  'Every breath you take, I'll be watching you'\n"
            "    ❌ 'រាល់ដង្ហើមដែលអ្នកដក ខ្ញុំនឹងមើលអ្នក'   ✅ 'រាល់ដង្ហើមរបស់អូន បងនៅតែមើលថែ'\n"
            "  'Let it go, let it go, can't hold it back anymore'\n"
            "    ❌ 'ទុកវាទៅ ទុកវាទៅ មិនអាចកាន់វាត្រឡប់ទៀតទេ'   ✅ 'លែងវាទៅ លែងខ្វល់ទៀតហើយ លែងអាចស៊ូទ្រាំទៀតហើយ'\n"
            "  'Oh my dear, this love is as sweet as orange juice'\n"
            "    ❌ 'អូស្ដី ក្ដីស្រឡាញ់នេះផ្អែមដូចទឹកផ្លុំក្រូច'   ✅ 'អូនអើយ ស្នេហ៍យើងផ្អែមល្អណាស់'\n"
            "Chinese → Khmer\n"
            "  '月亮代表我的心'\n"
            "    ❌ 'ព្រះច័ន្ទតំណាងបេះដូងរបស់ខ្ញុំ'   ✅ 'ព្រះច័ន្ទជាសាក្សីស្នេហ៍បង'\n"
            "Korean → Khmer\n"
            "  '사랑해요' (Saranghaeyo)\n"
            "    ❌ 'ស្រឡាញ់អ្នក'   ✅ 'បងស្រឡាញ់អូន'\n"
            "Thai → Khmer\n"
            "  'คิดถึงเธอทุกวัน'\n"
            "    ❌ 'គិតដល់អ្នករាល់ថ្ងៃ'   ✅ 'នឹកអូនរាល់ថ្ងៃមិនធ្លាប់ភ្លេច'\n"
            "Vietnamese → Khmer\n"
            "  'Yêu em thầm lặng'\n"
            "    ❌ 'ស្រឡាញ់អូនដោយស្ងាត់ៗ'   ✅ 'បងស្រឡាញ់អូនមិនហ៊ានប្រាប់'\n\n"
            "Those pairs teach the STYLE, not the answer. Never copy an example line into the song — "
            "write what THIS song actually says, in that style.\n"
            "If the Khmer you produce is letter-for-letter identical to one of the ✅ examples, "
            "you have not adapted the line, you have recycled it: rewrite it from the meaning.\n\n"

            "## SONG CONTEXT:\n"
            f"- Source language: {source_lang}\n"
            f"- Song title: {song_title or 'not provided'}\n"
            f"- Artist: {artist or 'not provided'}\n\n"

            "## OUTPUT FORMAT:\n"
            "Return ONLY a valid JSON array with one object per input line, in the same order:\n"
            "  [{\"id\": <original id>, \"text\": \"<Khmer line>\"}, ...]\n"
            "Each original line must get exactly one Khmer line: translate the IDEA of each line, "
            "not its letters, never transliterate the source, and add no explanations, notes or markdown.\n\n"
            f"## ORIGINAL LYRICS (line by line):\n{payload_str}"
        ).replace("{src}", source_lang)

    # ---- Naturalness guard -------------------------------------------------------
    # "Meaning-first, never letter-for-letter" is only useful if the studio can tell
    # whether a Khmer line actually landed. These cheap deterministic checks grade every
    # Khmer line and decide which drafts deserve a second, focused rewrite pass.

    _KHMER_LETTER_RE = re.compile(r'[\u1780-\u17FF]')
    _FOREIGN_LETTER_RE = re.compile(
        r'[A-Za-z\u0E00-\u0EFF\u1000-\u109F\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]'
    )

    # A Khmer line is graded in consonant units, the same proxy the timing engine uses for
    # word timestamps. Measured over the studio's real .km.srt / .srt corpus (183 Khmer lines):
    # median 17, p90 21, p97 22, longest 25 — so anything past 24 units is beyond what this
    # library of native lyrics ever asks a singer to hold, whatever the source length was.
    KHMER_LINE_UNIT_CAP = 24

    @staticmethod
    def _sung_syllables(text: str) -> int:
        """Counts sung units in a lyric line using the timing engine's convention.

        Khmer base consonants that do not hang below a coeng, one unit per CJK character, one
        per Latin vowel group. It is a proxy, not linguistics: a final consonant adds a unit,
        which is why the corpus above is what sets the caps, not a syllable theory.
        """
        if not text:
            return 0
        khmer = re.findall(r'(?<!\u17D2)[\u1780-\u17B3]', text)
        if khmer:
            return len(khmer)
        cjk = re.findall(r'[\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]', text)
        if cjk:
            return len(cjk)
        groups = re.findall(r'[aeiouyàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]+',
                            text, re.IGNORECASE)
        return len(groups)

    # Machine-translation tells that survive even when the line is clean Khmer script of sane
    # length: a possessive chain stacked the way English writes it, and a handful of calques the
    # model keeps producing for songs it has never heard sung in Khmer.
    _KHMER_CALQUES = (
        'បញ្ឈប់ការ',      # "stop the act of …" — word-for-word 'can't stop'
        'តំណាង',          # "represents" — the 月亮代表我的心 calque
        'ទឹកក្រូច',       # literal "orange juice" in a love line
        'ការស្រឡាញ់អ្នក',  # "the loving of you"
        'នូវពាក្យ',        # "the words of …" calque
    )

    def _khmer_line_issues(self, original: str, khmer: str) -> List[str]:
        """Why this Khmer line probably does not sound native yet (empty list means it does)."""
        if not str(khmer).strip():
            return ["empty"]
        text = str(khmer)
        src_syl = self._sung_syllables(original)
        km_syl = self._sung_syllables(text)
        issues: List[str] = []
        if not self._KHMER_LETTER_RE.search(text):
            issues.append("no_khmer")
        if self._FOREIGN_LETTER_RE.search(text):
            issues.append("foreign_letters")
        if text.strip() == str(original).strip():
            issues.append("unchanged")
        if src_syl >= 3 and km_syl <= 1:
            issues.append("meaning_dropped")
        # Cross-script unit counts are not comparable (Khmer writes a final consonant as its own
        # unit), so this only fires for lines that are un-singable on their own terms.
        if km_syl > max(self.KHMER_LINE_UNIT_CAP, int(src_syl * 3.2)):
            issues.append("too_long_to_sing")
        # '…នៃ…របស់…' is how a machine writes English possessives in Khmer letters; a Khmer
        # lyricist sings "បេះដូងបង", not "បេះដូងនៃជីវិតរបស់ខ្ញុំ".
        if text.count('នៃ') + text.count('របស់') >= 2:
            issues.append("stiff_possessive_chain")
        if any(cal in text for cal in self._KHMER_CALQUES):
            issues.append("literal_calque")
        return issues

    @staticmethod
    def _build_khmer_polish_prompt(
        source_lang: str,
        payload_str: str,
        song_title: str = "",
        artist: str = ""
    ) -> str:
        """Shared rewrite brief for the second pass.

        Used both by the automatic polish inside translation and by the manual
        "Fix Khmer with AI" button, so the two can never drift apart.
        """
        return (
            "You are an award-winning Khmer song lyricist doing the final rewrite of translated "
            "lyrics. The Khmer drafts below were produced by machine translation and are too "
            "literal, too long, or leak foreign letters.\n"
            f"The original song is in {source_lang}. Song title: {song_title or 'not provided'}. "
            f"Artist: {artist or 'not provided'}.\n"
            "For each line: the 'original' text carries the MEANING you must keep; the 'khmer' text "
            "is only a draft, so feel free to throw its wording away. 'issue' says what the studio's "
            "naturalness grader found — fix exactly that:\n"
            "  • no_khmer / unchanged — the line is still in the source language: write Khmer.\n"
            "  • foreign_letters — foreign or romanised letters are stuck inside: say it in Khmer words.\n"
            "  • literal_calque — a word-for-word calque (បញ្ឈប់ការ, តំណាង, ទឹកក្រូច…): replace the "
            "calqued phrase with what a Khmer singer would actually say.\n"
            "  • stiff_possessive_chain — '…នៃ…របស់…' is English grammar in Khmer letters: rebuild the "
            "possessive the Khmer way (បេះដូងបង, not បេះដូងនៃជីវិតរបស់ខ្ញុំ).\n"
            "  • too_long_to_sing — the line cannot fit the cue: cut it short, keep the feeling.\n"
            "  • meaning_dropped / empty — too little was said: give the line its full meaning.\n\n"
            "REWRITE RULES (the same brief as the first pass):\n"
            "1. Meaning first, never letter-for-letter (បកប្រែតាមអត្ថន័យ មិនតាមអក្សរ). "
            "Must sound like natural, native Khmer (ត្រូវតែស្ដាប់ជាខ្មែរធម្មជាតិ).\n"
            "   - Fix unnatural metaphors, literal food names, or stiff grammar.\n"
            "   - Example: ❌ 'ប្រណាំងទូកហើយញ៉ាំបាយជាមួយគ្នា អយស្ទ័រនិងទឹកអំពិល' -> ✅ 'ប្រណាំងទូកហើយញ៉ាំត្រីកែវជ្រលក់ទឹកត្រីអំពិល'\n"
            "   - Example: ❌ 'ឋានសួគ៌គឺអង្គុយក្បែរមាត់ស្រះជាមួយមនុស្សជាទីស្រឡាញ់' -> ✅ 'ទោះនៅបាតអណ្ដូងក៏ជាឋានសួគ៌ឱ្យតែបាននៅក្បែរអូន'\n"
            "2. Everyday Khmer words a listener understands on first hearing; no heavy "
            "Pali/Sanskrit stacks, no formal register in a love song.\n"
            "3. Singable length: stay close to the length of the original line and under roughly 24 "
            "sung units (Khmer base consonants) — longer than that cannot fit the cue. "
            "Two short clauses beat one long phrase.\n"
            "4. Preserve the emotion and meaning of the original line — never invent new content.\n"
            "5. Use one consistent pronoun pair (បង/អូន for romance) across every line; never mix "
            "អ្នក with អូន for the same person.\n"
            "6. Output Khmer script only (អក្សរខ្មែរ). No foreign letters and no romanization.\n"
            "7. STRICT 1:1 LINE INTEGRITY: exactly 1 output line per input line, same id and order, "
            "never merge or split lines.\n"
            "8. Return ONLY a valid JSON array of objects with schema:\n"
            '[{"id": 0, "text": "..."}]\n\n'
            f"Lines to rewrite:\n{payload_str}"
        )

    @staticmethod
    def _parse_id_text(res_str: str, require_id: bool = False) -> Dict[str, str]:
        """Reads an id/text JSON reply as tolerantly as the models actually deliver it.

        Gemini occasionally wraps the array in a ```json fence, in a sentence of prose, or in an
        object such as {"translations": [...]}, and names the field 'translation' instead of
        'text'. Every one of those shapes used to raise inside json.loads and cost the whole
        button press, so the shape is repaired here instead of failing the request.

        require_id is used by chunked rewrite passes: without an explicit id a line could be
        written back onto the wrong neighbour, so those replies are dropped rather than guessed.
        """
        raw = str(res_str or "").strip()
        if not raw:
            return {}

        tries = [raw]
        lb, rb = raw.find("["), raw.rfind("]")
        if 0 <= lb < rb:
            tries.append(raw[lb:rb + 1])
        lc, rc = raw.find("{"), raw.rfind("}")
        if 0 <= lc < rc:
            tries.append(raw[lc:rc + 1])

        data = None
        for candidate in tries:
            try:
                data = json.loads(candidate)
                break
            except Exception:
                continue
        if data is None:
            return {}

        text_keys = ("text", "translation", "translated_text", "khmer", "value", "output")
        if isinstance(data, dict):
            items = next((v for v in data.values() if isinstance(v, list)), None)
            items = items if items is not None else [data]
        elif isinstance(data, list):
            items = data
        else:
            return {}

        parsed: Dict[str, str] = {}
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            text = ""
            for key in text_keys:
                value = str(item.get(key) or "").strip()
                if value:
                    text = value
                    break
            if not text:
                continue
            item_id = item.get("id", item.get("line_id"))
            if item_id is None:
                if require_id:
                    continue
                item_id = i
            parsed[str(item_id)] = text
        return parsed

    def _polish_khmer_pairs(
        self,
        pairs: List[Dict[str, Any]],
        source_lang: str,
        song_title: str = "",
        artist: str = ""
    ) -> Dict[str, str]:
        """Runs the rewrite brief over {id, original, khmer, issue} objects, in chunks."""
        fixed: Dict[str, str] = {}
        CHUNK = 30
        for start in range(0, len(pairs), CHUNK):
            chunk = pairs[start:start + CHUNK]
            payload_str = json.dumps(chunk, ensure_ascii=False)
            prompt = self._build_khmer_polish_prompt(
                source_lang, payload_str, song_title=song_title, artist=artist
            )
            try:
                res_str = call_gemini_api(
                    prompt, json_mode=True,
                    timeout=self.KHMER_ATTEMPT_TIMEOUT_S,
                    total_timeout=self.KHMER_POLISH_TIMEOUT_S
                )
                if not res_str:
                    continue
                fixed.update(self._parse_id_text(res_str))
            except Exception as e:
                print(f"[Khmer Polish] Gemini call notice: {e}")
        return fixed

    def _grade_and_polish_khmer(
        self,
        result_data: List[Dict[str, Any]],
        source_texts: List[str],
        source_lang: str,
        song_title: str = "",
        artist: str = ""
    ) -> List[Dict[str, Any]]:
        """Grades every Khmer line, then rewrites only the ones that fail the ear test.

        A rewrite replaces the draft only when it scores strictly fewer problems, so the second
        pass can never make a line worse. Each line carries 'naturalness' for the API and UI.
        """
        flagged: List[Dict[str, Any]] = []
        pos_by_id: Dict[str, int] = {}
        for i, line in enumerate(result_data):
            original = str(source_texts[i]) if i < len(source_texts) else ""
            draft = str(line.get("text", ""))
            issues = self._khmer_line_issues(original, draft)
            line["naturalness"] = {"status": "still_literal" if issues else "natural", "issues": issues}
            if issues:
                line_id = str(line.get("line_id", i))
                flagged.append({
                    "id": line_id,
                    "original": original.strip(),
                    "khmer": draft.strip(),
                    "issue": ", ".join(issues)
                })
                pos_by_id[line_id] = i

        if flagged:
            fixed = self._polish_khmer_pairs(flagged, source_lang, song_title=song_title, artist=artist)
            for item in flagged:
                candidate = fixed.get(str(item.get("id")), "")
                pos = pos_by_id.get(str(item.get("id")))
                if not candidate or pos is None or pos >= len(result_data):
                    continue
                try:
                    from backend.lyric_engine import normalize_khmer_orthography
                    candidate = normalize_khmer_orthography(candidate)
                except Exception:
                    pass
                remaining = self._khmer_line_issues(item["original"], candidate)
                line = result_data[pos]
                draft_issues = [x for x in item["issue"].split(", ") if x]
                if len(remaining) >= len(draft_issues):
                    continue  # the rewrite did not help — keep the better draft
                line["text"] = candidate
                line["words"] = []
                line["naturalness"] = {
                    "status": "polished" if not remaining else "still_literal",
                    "issues": remaining
                }
        return result_data

    def khmer_naturalness_summary(self, lines: List[Dict[str, Any]]) -> Dict[str, int]:
        """Counts how many Khmer lines read as native, were rewritten, or still need a human."""
        natural = polished = literal = 0
        for l in lines:
            status = str((l.get("naturalness") or {}).get("status") or "")
            if status == "natural":
                natural += 1
            elif status == "polished":
                polished += 1
            elif status == "still_literal":
                literal += 1
        return {"natural": natural, "polished": polished, "still_literal": literal}

    def translate_lyrics_data(
        self,
        lyrics_data: List[Dict[str, Any]],
        target_lang: str = "Khmer",
        song_title: str = "",
        artist: str = "",
        auto_polish: bool = True
    ) -> List[Dict[str, Any]]:
        """Translates an array of lyrics_data objects to the target language using Gemini.

        When the target is Khmer the culturally-adapted brief is used and, by default, the
        result is graded for naturalness: any line that still reads word-for-word, keeps foreign
        letters or is too long to sing gets one focused rewrite before it is returned. auto_polish
        can be turned off to save a request, and song title / artist steer pronoun choice (បង/អូន).
        """
        if not lyrics_data:
            return lyrics_data

        # Create a simplified array with only line_id and text to save tokens
        simplified_lines = []
        for i, l in enumerate(lyrics_data):
            simplified_lines.append({
                "id": l.get("line_id", i),
                "text": l.get("text", "")
            })

        import json
        payload_str = json.dumps(simplified_lines, ensure_ascii=False)

        # Detect whether to use the rich Khmer cultural prompt
        is_khmer_target = target_lang.lower().strip() in ("khmer", "km", "cambodian", "ខ្មែរ")

        if is_khmer_target:
            texts = [l.get("text", "") for l in lyrics_data]
            source_lang = self._detect_source_language(texts)
            prompt = self._build_khmer_translation_prompt(
                source_lang, payload_str, song_title=song_title, artist=artist
            )
        else:
            prompt = (
                f"You are a professional song lyric translator. Translate the following lyrics to {target_lang}. "
                "Translate naturally — do NOT translate word-by-word. "
                "Keep the poetic tone, emotion, and singability intact. "
                "The translation should sound like it was originally written in the target language. "
                f"Song title: {song_title or 'not provided'}. Artist: {artist or 'not provided'}. "
                "IMPORTANT: Return ONLY a valid JSON array of objects. Each object MUST have an 'id' (matching the original) and a 'text' (the translated text). "
                "One translated line per input line, same order, no notes.\n"
                f"Input:\n{payload_str}"
            )

        # Gemini sometimes echoes the input back instead of translating it. A single-line
        # Khmer → English request reproduced exactly that in testing: attempt 1 returned the
        # source unchanged, attempt 2 returned "I love you, but I'm too afraid to say." One
        # bounded retry turns that into a working translation instead of a failed button press.
        src_by_id = {str(s["id"]): str(s["text"]).strip() for s in simplified_lines}
        trans_map: Dict[str, str] = {}
        for attempt in (1, 2):
            try:
                res_str = call_gemini_api(
                    prompt, json_mode=True,
                    timeout=self.KHMER_ATTEMPT_TIMEOUT_S if is_khmer_target else 30,
                    total_timeout=self.KHMER_DRAFT_TIMEOUT_S if is_khmer_target else 60
                )
            except Exception as e:
                print(f"[Lyric Translator] Gemini request failed: {e}")
                continue
            if not res_str:
                continue
            parsed = self._parse_id_text(res_str, require_id=True)
            if not parsed:
                if attempt == 1:
                    print("[Lyric Translator] the reply was not usable id/text JSON, retrying once")
                continue
            trans_map = parsed
            if any(str(v).strip() and str(v).strip() != src_by_id.get(k, "\x00")
                   for k, v in trans_map.items()):
                break
            if attempt == 1:
                print("[Lyric Translator] the model echoed the source lines, retrying once")

        # Map back to original structure. This runs even when a request or the grading pass below
        # fails, because throwing away a usable draft is worse than returning an ungraded one.
        result_data = []
        for i, l in enumerate(lyrics_data):
            new_l = dict(l)
            line_id = str(l.get("line_id", i))
            if line_id in trans_map and trans_map[line_id].strip():
                new_l["text"] = trans_map[line_id]
                # Clear word-level timings because they are no longer valid for translated text
                new_l["words"] = []
            result_data.append(new_l)
        if is_khmer_target and auto_polish and trans_map:
            try:
                result_data = self._grade_and_polish_khmer(
                    result_data, texts, source_lang, song_title=song_title, artist=artist
                )
            except Exception as e:
                print(f"[Khmer Naturalness] grading pass failed, keeping the ungraded draft: {e}")
        return result_data

    def refine_khmer_lyrics(
        self,
        pairs: List[Dict[str, Any]],
        song_title: str = "",
        artist: str = "",
        source_lang: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        AI-Powered Native Khmer Refinement:
        Rewrites translated Khmer lyrics into natural, singable, native Khmer like a song
        originally composed in Khmer, fixing literal/machine translations, unnatural phrasing,
        and preserving exact 1:1 line ordering and timestamps.

        Shares one rewrite brief with the automatic polish inside translate_lyrics_data, and
        grades both draft and rewrite so a "fix" can never replace a good line with a worse one.
        """
        if not pairs:
            return pairs

        # Detect source language if not specified
        if not source_lang:
            originals = [str(p.get("original", "")).strip() for p in pairs if p.get("original")]
            source_lang = self._detect_source_language(originals) if originals else "Vietnamese"

        simplified = []
        for i, p in enumerate(pairs):
            original = str(p.get("original", "")).strip()
            khmer = str(p.get("khmer", "")).strip()
            issues = self._khmer_line_issues(original, khmer) if khmer else ["empty"]
            simplified.append({
                "id": p.get("id", i),
                "original": original,
                "khmer": khmer,
                "issue": ", ".join(issues)
            })

        fixed = self._polish_khmer_pairs(
            simplified, source_lang, song_title=song_title, artist=artist
        )

        try:
            from backend.lyric_engine import normalize_khmer_orthography
        except Exception:
            normalize_khmer_orthography = None

        out = []
        for i, item in enumerate(simplified):
            copied = dict(pairs[i]) if i < len(pairs) else {}
            pid = str(item.get("id"))
            candidate = str(fixed.get(pid, "")).strip()
            draft = item["khmer"]
            draft_issues = [x for x in item["issue"].split(", ") if x]
            if candidate:
                if normalize_khmer_orthography:
                    try:
                        candidate = normalize_khmer_orthography(candidate)
                    except Exception:
                        pass
                new_issues = self._khmer_line_issues(item["original"], candidate)
                # Accept the rewrite unless it scores strictly worse than what we already had.
                if len(new_issues) <= len(draft_issues):
                    copied["text"] = candidate
                    copied["naturalness"] = {
                        "status": "polished" if not new_issues else "still_literal",
                        "issues": new_issues
                    }
                else:
                    copied["text"] = draft or item["original"]
                    copied["naturalness"] = {"status": "still_literal", "issues": draft_issues}
            else:
                # No rewrite came back: keep the draft, normalising the orthography if we can.
                fallback = draft or item["original"]
                if normalize_khmer_orthography and fallback:
                    try:
                        fallback = normalize_khmer_orthography(fallback)
                    except Exception:
                        pass
                copied["text"] = fallback
                copied["naturalness"] = {
                    "status": "natural" if not draft_issues else "still_literal",
                    "issues": draft_issues
                }
            out.append(copied)
        return out

llm_engine = LocalLLMEngine()


def normalize_text_for_sim(text: str) -> str:
    """Normalizes text for cross-lingual / phonetic similarity matching."""
    t = text.lower()
    t = unicodedata.normalize('NFD', t)
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    t = re.sub(r'[^\w\s]', '', t)
    return ' '.join(t.split())


def calc_text_sim(s1: str, s2: str) -> float:
    """Calculates text similarity using Levenshtein ratio and word Jaccard overlap."""
    n1 = normalize_text_for_sim(s1)
    n2 = normalize_text_for_sim(s2)
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0
    ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
    w1, w2 = set(n1.split()), set(n2.split())
    jaccard = len(w1 & w2) / max(len(w1), len(w2)) if w1 and w2 else 0.0
    return max(ratio, jaccard)


SPAM_PATTERNS = [
    r'subscribe', r'kênh', r'ghiền mì gõ', r'la la school', r'đăng ký',
    r'theo dõi', r'bỏ lỡ', r'video hấp dẫn', r'like and subscribe',
    r'thank you for watching', r'subscribers', r'amara\.org', r'cảm ơn các bạn',
    r'hãy nhấn chuông', r'thông báo', r'chúc các bạn'
]
SPAM_REGEX = re.compile('|'.join(SPAM_PATTERNS), re.IGNORECASE)


def align_and_correct_lyrics_with_reference(
    lyrics_data: List[Dict[str, Any]],
    reference_text: str,
    audio_path: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Studio-grade Alignment & Correction Engine:
    Aligns automated speech-to-text / Whisper transcription lines with
    user-provided ground-truth original lyrics text.
    
    1. Extracts and cleans 100% authentic reference lines in exact order.
    2. Cross-references verified studio subtitles (.lrc, .vtt) if present.
    3. Detects and purges Whisper YouTube hallucinations ('subscribe', 'Ghiền Mì Gõ', etc.).
    4. Global Sequence Alignment (Needleman-Wunsch DP) to map reference lines to audio cues.
    5. Merges split cues and partitions merged phrases.
    6. Interpolates missing stanzas smoothly.
    7. Acoustically snaps timestamps to singer vocal onsets via VAD.
    8. Automatically tokenizes and synchronizes word-level timestamps.
    9. Persists synchronized .lrc / .vi.lrc / .km.lrc to disk.
    """
    import difflib
    import unicodedata
    import re
    import json

    if not reference_text or not reference_text.strip():
        if lyrics_data:
            from backend.lyric_engine import double_check_lyrics
            return double_check_lyrics(lyrics_data)
        return [], {"changes_count": 0, "status": "No lyrics to align"}

    # Step 1: Clean and extract authentic reference lines
    raw_lines = [l.strip() for l in reference_text.splitlines() if l.strip()]
    ref_lines: List[str] = []
    for l in raw_lines:
        # Ignore LRC metadata header tags
        if re.match(r'^\[(?:ti|ar|al|by|offset|length|re|ve):.*?\]', l, re.IGNORECASE):
            continue
        cleaned = re.sub(r'^(?:#+|\*+|-+|\d+[\.\)]|[A-Za-z]+\s*\d+:)\s*', '', l).strip()
        cleaned = re.sub(r'^\[\d{1,2}:\d{2}(?:\.\d+)?\]\s*', '', cleaned)
        cleaned = re.sub(r'^\d{2}:\d{2}(?:\.\d+)?\s*-->\s*\d{2}:\d{2}(?:\.\d+)?\s*', '', cleaned)
        if cleaned:
            ref_lines.append(cleaned)

    if not ref_lines:
        return lyrics_data, {"changes_count": 0, "status": "empty_reference"}

    total_ref = len(ref_lines)
    candidate_cues: List[Dict[str, Any]] = []
    used_source = "whisper_transcript"

    # Step 2: Check for existing studio subtitle files next to audio
    best_sub_cues = []
    best_sub_score = 0
    best_sub_name = ""

    if audio_path and os.path.exists(audio_path):
        from backend.lyric_engine import parse_subtitle_file
        base_no_ext = os.path.splitext(audio_path)[0]
        audio_dir = os.path.dirname(audio_path)
        base_name = os.path.basename(base_no_ext)

        possible_subs = []
        for ext in [".en.vtt", ".vtt", ".lrc", ".vi.lrc", ".km.lrc", ".srt"]:
            p = base_no_ext + ext
            if os.path.exists(p):
                possible_subs.append(p)

        # Also search in directory for matching name
        if os.path.exists(audio_dir):
            for f in os.listdir(audio_dir):
                if f.lower().endswith(('.lrc', '.vtt', '.srt')):
                    full_p = os.path.join(audio_dir, f)
                    if full_p not in possible_subs:
                        if calc_text_sim(f, base_name) > 0.5:
                            possible_subs.append(full_p)

        for sub_p in possible_subs:
            try:
                parsed = parse_subtitle_file(sub_p, audio_path=audio_path)
                if parsed and len(parsed) >= 4:
                    # Score against ref_lines
                    matches_cnt = 0
                    for r_line in ref_lines[:10]:
                        if any(calc_text_sim(r_line, c.get("text", "")) >= 0.45 for c in parsed[:20]):
                            matches_cnt += 1
                    if matches_cnt > best_sub_score:
                        best_sub_score = matches_cnt
                        best_sub_cues = parsed
                        best_sub_name = os.path.basename(sub_p)
            except Exception:
                pass

    if best_sub_cues and best_sub_score >= 2:
        candidate_cues = best_sub_cues
        used_source = f"studio_subtitle ({best_sub_name})"

    # If no subtitle file was found or matched, use lyrics_data
    if not candidate_cues and lyrics_data:
        for cue in lyrics_data:
            t = cue.get("text", "").strip()
            if not t:
                continue
            if re.match(r'^(?:\[.*?\]|♪+|♫+|\.+|-+)$', t):
                continue
            if SPAM_REGEX.search(t):
                max_s = max([calc_text_sim(t, r) for r in ref_lines]) if ref_lines else 0
                if max_s < 0.35:
                    continue
            candidate_cues.append(dict(cue))

    if not candidate_cues:
        # Use Acoustic Vocal Alignment to anchor lyrics to real singer onsets
        if audio_path and os.path.exists(audio_path):
            try:
                from backend.vocal_align import force_align_lyrics_to_audio
                aligned = force_align_lyrics_to_audio(ref_lines, audio_path=audio_path)
                if aligned and len(aligned) > 0:
                    return aligned, {"changes_count": len(aligned), "model_used": "Acoustic Vocal Forced Alignment", "source": "vad_alignment"}
            except Exception as e:
                pass

        duration = 180.0
        if audio_path and os.path.exists(audio_path):
            try:
                from backend.audio_analyzer import decode_audio_to_numpy
                _, _, duration = decode_audio_to_numpy(audio_path, target_sr=8000)
            except Exception:
                pass
        step = max(3.0, (duration - 6.0) / max(1, total_ref))
        result = []
        for i, text in enumerate(ref_lines):
            st = round(3.0 + i * step, 2)
            et = round(min(duration, st + step * 0.9), 2)
            result.append({
                "line_id": i,
                "start": st,
                "end": et,
                "text": text,
                "words": []
            })
        return result, {"changes_count": total_ref, "model_used": "Proportional Spacing", "source": "fallback"}

    # Step 3: Flexible Multi-Span Sequence Alignment (1-to-1, 1-to-many, many-to-1)
    aligned_lines: List[Dict[str, Any]] = [
        {'line_id': idx, 'text': r, 'start': None, 'end': None, 'matched': False}
        for idx, r in enumerate(ref_lines)
    ]

    c_idx = 0
    r_idx = 0
    num_cues = len(candidate_cues)
    num_refs = len(ref_lines)

    while r_idx < num_refs and c_idx < num_cues:
        r_line = ref_lines[r_idx]

        # 1. Test 1 ref line vs 1 cue
        sim_1_1 = calc_text_sim(r_line, candidate_cues[c_idx].get('text', ''))

        # 2. Test 1 ref line vs (cue[c_idx] + cue[c_idx+1]) (cue was split across 2 segments)
        sim_1_2 = 0.0
        if c_idx + 1 < num_cues:
            combo_cues = candidate_cues[c_idx].get('text', '') + ' ' + candidate_cues[c_idx + 1].get('text', '')
            sim_1_2 = calc_text_sim(r_line, combo_cues)

        # 3. Test (ref[r_idx] + ref[r_idx+1]) vs 1 cue (cue contains 2 short ref lines)
        sim_2_1 = 0.0
        if r_idx + 1 < num_refs:
            combo_ref = r_line + ' ' + ref_lines[r_idx + 1]
            sim_2_1 = calc_text_sim(combo_ref, candidate_cues[c_idx].get('text', ''))

        best_score = max(sim_1_1, sim_1_2, sim_2_1)

        if best_score < 0.42:
            # Check lookahead in candidate cues (e.g. skip instrumental break or whisper noise)
            found_ahead = False
            for la in range(1, 5):
                if c_idx + la < num_cues:
                    s = calc_text_sim(r_line, candidate_cues[c_idx + la].get('text', ''))
                    if s >= 0.50:
                        c_idx += la
                        found_ahead = True
                        break
            if found_ahead:
                continue
            r_idx += 1
            continue

        if best_score == sim_1_2 and sim_1_2 >= 0.55:
            # 1 ref line spans 2 cues
            aligned_lines[r_idx]['start'] = float(candidate_cues[c_idx].get('start', 0.0))
            aligned_lines[r_idx]['end'] = float(candidate_cues[c_idx + 1].get('end', candidate_cues[c_idx].get('start', 0.0) + 3.0))
            aligned_lines[r_idx]['matched'] = True
            c_idx += 2
            r_idx += 1
        elif best_score == sim_2_1 and sim_2_1 >= 0.55:
            # 1 cue contains 2 ref lines
            c_st = float(candidate_cues[c_idx].get('start', 0.0))
            c_et = float(candidate_cues[c_idx].get('end', c_st + 4.0))
            c_dur = max(1.5, c_et - c_st)
            l1 = len(ref_lines[r_idx])
            l2 = len(ref_lines[r_idx + 1])
            t_split = c_st + c_dur * (l1 / max(1, l1 + l2))
            aligned_lines[r_idx]['start'] = round(c_st, 2)
            aligned_lines[r_idx]['end'] = round(t_split, 2)
            aligned_lines[r_idx]['matched'] = True
            aligned_lines[r_idx + 1]['start'] = round(t_split + 0.1, 2)
            aligned_lines[r_idx + 1]['end'] = round(c_et, 2)
            aligned_lines[r_idx + 1]['matched'] = True
            c_idx += 1
            r_idx += 2
        else:
            aligned_lines[r_idx]['start'] = float(candidate_cues[c_idx].get('start', 0.0))
            aligned_lines[r_idx]['end'] = float(candidate_cues[c_idx].get('end', candidate_cues[c_idx].get('start', 0.0) + 3.0))
            aligned_lines[r_idx]['matched'] = True
            c_idx += 1
            r_idx += 1

    # Step 4: Interpolate unanchored lines smoothly
    first_match_idx = next((i for i, l in enumerate(aligned_lines) if l['matched']), None)
    if first_match_idx is not None and first_match_idx > 0:
        first_start = aligned_lines[first_match_idx]['start']
        step = max(2.5, min(4.5, (first_start - 2.0) / first_match_idx))
        for i in range(first_match_idx - 1, -1, -1):
            target_start = max(1.0, aligned_lines[i + 1]['start'] - step)
            target_end = aligned_lines[i + 1]['start'] - 0.2
            aligned_lines[i]['start'] = round(target_start, 2)
            aligned_lines[i]['end'] = round(max(target_start + 1.5, target_end), 2)

    last_anchored = None
    for i in range(len(aligned_lines)):
        if aligned_lines[i]['start'] is not None:
            if last_anchored is not None and i > last_anchored + 1:
                prev_end = aligned_lines[last_anchored]['end']
                next_start = aligned_lines[i]['start']
                gap = next_start - prev_end
                unanchored_count = i - last_anchored - 1
                if gap > 1.0:
                    step = gap / (unanchored_count + 1)
                    for k_idx, u_i in enumerate(range(last_anchored + 1, i)):
                        u_start = prev_end + step * (k_idx + 0.3)
                        u_end = prev_end + step * (k_idx + 1.1)
                        aligned_lines[u_i]['start'] = round(u_start, 2)
                        aligned_lines[u_i]['end'] = round(min(next_start - 0.2, u_end), 2)
                else:
                    for k_idx, u_i in enumerate(range(last_anchored + 1, i)):
                        aligned_lines[u_i]['start'] = round(prev_end + k_idx * 0.5, 2)
                        aligned_lines[u_i]['end'] = round(prev_end + (k_idx + 1) * 0.5, 2)
            last_anchored = i

    if last_anchored is not None and last_anchored < len(aligned_lines) - 1:
        prev_end = aligned_lines[last_anchored]['end']
        for k_idx, u_i in enumerate(range(last_anchored + 1, len(aligned_lines))):
            aligned_lines[u_i]['start'] = round(prev_end + k_idx * 3.5, 2)
            aligned_lines[u_i]['end'] = round(prev_end + (k_idx + 1) * 3.5 - 0.3, 2)

    # Step 6: VAD Acoustic Snap (if audio is accessible)
    vocal_onsets_fine: List[float] = []
    if audio_path and os.path.exists(audio_path):
        try:
            from backend.vocal_align import detect_vocal_segments, detect_vocal_onsets
            vocal_segments = detect_vocal_segments(audio_path)
            if vocal_segments:
                vocal_onsets_fine = detect_vocal_onsets(audio_path, vocal_segments)
                vocal_onsets = [seg[0] for seg in vocal_segments]
                for l in aligned_lines:
                    orig_s = l['start']
                    if orig_s is None:
                        continue
                    orig_dur = max(1.5, (l['end'] or orig_s + 3.0) - orig_s)
                    best_onset = orig_s
                    best_dist = 0.45
                    for onset in vocal_onsets:
                        d = abs(onset - orig_s)
                        if d < best_dist:
                            best_dist = d
                            best_onset = onset
                    if best_onset != orig_s:
                        l['start'] = round(float(best_onset), 2)
                        l['end'] = round(float(best_onset + orig_dur), 2)
        except Exception as vad_e:
            print(f"[Lyric Align] VAD notice: {vad_e}")

    # Step 7: Monotonicity & Word-Level Formatting
    from backend.vocal_align import time_line_words
    final_lyrics: List[Dict[str, Any]] = []
    prev_end = 0.0
    for i, line in enumerate(aligned_lines):
        st = max(0.0, float(line.get('start') or 0.0))
        et = max(st + 1.2, float(line.get('end') or st + 3.0))
        if st < prev_end:
            st = round(prev_end + 0.1, 2)
            et = max(et, round(st + 1.2, 2))
        prev_end = et

        text = line['text']
        words = time_line_words(text, round(st, 2), round(et, 2), onsets=vocal_onsets_fine)

        final_lyrics.append({
            "line_id": i,
            "start": round(st, 2),
            "end": round(et, 2),
            "text": text,
            "words": words
        })

    # Step 8: Persist to disk (.lrc and .vi.lrc / .km.lrc) if audio_path exists
    if audio_path and os.path.exists(audio_path):
        try:
            base_no_ext = os.path.splitext(audio_path)[0]
            lrc_lines = []
            for l in final_lyrics:
                s = l["start"]
                mins = int(s // 60)
                secs = s % 60
                lrc_lines.append(f"[{mins:02d}:{secs:05.2f}] {l['text']}")
            lrc_text = "\n".join(lrc_lines)

            sample_t = " ".join([l["text"] for l in final_lyrics[:6]])
            is_km = any('\u1780' <= c <= '\u17FF' for c in sample_t)
            is_vi = any(c in 'àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ' for c in sample_t.lower())
            
            dest_paths = [base_no_ext + ".lrc"]
            if is_km:
                dest_paths.append(base_no_ext + ".km.lrc")
            elif is_vi:
                dest_paths.append(base_no_ext + ".vi.lrc")

            for dest in dest_paths:
                with open(dest, "w", encoding="utf-8") as f:
                    f.write(lrc_text)
            print(f"[Lyric Align] ✅ Persisted {len(final_lyrics)} lines to {dest_paths}")
        except Exception as save_e:
            print(f"[Lyric Align] Save notice: {save_e}")

    report = {
        "status": "success",
        "lines_count": len(final_lyrics),
        "changes_count": len(final_lyrics),
        "source": used_source,
        "model_used": "VIDA Dynamic Monotonic Align & VAD Engine"
    }
    return final_lyrics, report


