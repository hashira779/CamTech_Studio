import os
from typing import Dict, Any, Optional

class LocalLLMEngine:
    """
    LocalLLMEngine integrates with llama.cpp to run highly optimized GGUF 
    local models (like SeaLLMs) on CPU RAM at blazing fast speeds.
    """
    def __init__(self):
        self.llm = None
        self.is_loaded = False
        self.has_warned = False
        
    def load_model(self):
        if self.is_loaded:
            return
        try:
            from llama_cpp import Llama
            
            # The downloaded model path
            model_path = os.path.join(os.path.dirname(__file__), "..", "models", "SeaLLMs-v3-1.5B-Chat.Q4_K_M.gguf")
            model_path = os.path.abspath(model_path)
            
            if not os.path.exists(model_path):
                if not self.has_warned:
                    print(f"[LLM Engine] Model file not found at {model_path}. Using smart offline semantic analyzer.")
                    self.has_warned = True
                self.is_loaded = True
                return
                
            print(f"[LLM Engine] Loading 4-bit Quantized GGUF model into CPU RAM...")
            # n_ctx is context window, n_threads automatically uses CPU cores
            self.llm = Llama(model_path=model_path, n_ctx=2048, verbose=False)
            self.is_loaded = True
            print("[LLM Engine] GGUF Model loaded successfully.")
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

    def _smart_fallback_analysis(self, text: str) -> str:
        """Intelligent semantic and mood analyzer for Khmer, Vietnamese, and multilingual lyrics."""
        t = text.lower()
        
        # Check script / language
        has_khmer = any(0x1780 <= ord(c) <= 0x17FF for c in text)
        
        mood = "Melodic & Emotional"
        themes = []
        style_rec = "Fluid Wave (Neon Glow)"
        
        # Keyword heuristic checks
        if any(w in t for w in ["ស្នេហា", "ស្រឡាញ់", "love", "heart", "yêu", "tình", "miss", "បេះដូង", "ចាំ"]):
            mood = "Romantic & Sentimental"
            themes.append("Love & Longing (មនោសញ្ចេតនា)")
            style_rec = "Angkor Mandala / Sunset Glow"
        elif any(w in t for w in ["យំ", "ឈឺ", "sad", "pain", "tears", "khóc", "sầu", "បែក", "ព្រាត់", "ឯកា"]):
            mood = "Melancholic & Reflective"
            themes.append("Heartbreak & Solitude (ការព្រាត់ប្រាស)")
            style_rec = "Horizon Wave / Deep Blue Cyberpunk"
        elif any(w in t for w in ["រាំ", "សប្បាយ", "dance", "party", "fire", "bass", "vui", "club", "jump"]):
            mood = "Energetic & Uplifting"
            themes.append("High Energy Dance (ចង្វាក់រស់រវើក)")
            style_rec = "Trap Nation / Hyper Liquid Pulse"
        elif any(w in t for w in ["យុគមាស", "ស៊ីសាមុត", "បុរាណ", "vintage", "retro", "classic", "ចំប៉ា", "បាត់ដំបង"]):
            mood = "Golden Era Nostalgic (យុគមាស)"
            themes.append("Cambodian 60s Vinyl Heritage")
            style_rec = "Vintage Vinyl (ស៊ីន ស៊ីសាមុត 33⅓ RPM)"
        else:
            themes.append("Poetic Narrative & Musical Expression")
            
        lang_label = "Khmer (ភាសាខ្មែរ)" if has_khmer else "Multilingual"
        
        return (
            f"🎵 **Language**: {lang_label}\n"
            f"✨ **Mood**: {mood}\n"
            f"📝 **Themes**: {', '.join(themes)}\n"
            f"🎨 **Recommended Visual Style**: {style_rec}"
        )

    def analyze_text(self, text: str) -> Dict[str, Any]:
        """Analyzes text in any language for sentiment, meaning, mood, and lyrical themes."""
        if not self.is_loaded:
            self.load_model()
            
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

llm_engine = LocalLLMEngine()
