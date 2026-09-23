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
        
    def load_model(self):
        if self.is_loaded:
            return
        try:
            from llama_cpp import Llama
            
            # The downloaded model path
            model_path = os.path.join(os.path.dirname(__file__), "..", "models", "SeaLLMs-v3-1.5B-Chat.Q4_K_M.gguf")
            model_path = os.path.abspath(model_path)
            
            if not os.path.exists(model_path):
                print(f"[LLM Engine] Model file not found at {model_path}. Please run download_model.py")
                return
                
            print(f"[LLM Engine] Loading 4-bit Quantized GGUF model into CPU RAM...")
            # n_ctx is context window, n_threads automatically uses CPU cores
            self.llm = Llama(model_path=model_path, n_ctx=2048, verbose=False)
            self.is_loaded = True
            print("[LLM Engine] GGUF Model loaded successfully.")
        except ImportError:
            print("[LLM Engine] Warning: 'llama_cpp' not installed.")
        except Exception as e:
            print(f"[LLM Engine] Error loading model: {e}")

    def analyze_khmer_text(self, text: str) -> Dict[str, Any]:
        """Analyzes Khmer text using the CPU-loaded SeaLLMs GGUF."""
        if not self.is_loaded:
            self.load_model()
            
        if self.llm is None:
            return {"status": "error", "analysis": "Model not loaded. Missing GGUF file.", "text": text}
            
        prompt = f"Analyze the following Khmer text for sentiment, meaning, and spelling accuracy:\n\n{text}\n\nAnalysis:"
        
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
            
    def translate_to_khmer(self, english_text: str) -> str:
        """Translates English to Khmer."""
        if not self.is_loaded:
            self.load_model()
        if self.llm is None:
            return "[Translation Failed - No Model]"
            
        prompt = f"Translate the following English text to Khmer:\n\n{english_text}\n\nTranslation:"
        try:
            output = self.llm(prompt, max_tokens=100, temperature=0.1, stop=["\n\n"])
            return output['choices'][0]['text'].strip()
        except Exception as e:
            return f"Error: {e}"

llm_engine = LocalLLMEngine()
