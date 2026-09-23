import os
from huggingface_hub import hf_hub_download

MODEL_REPO = "SeaLLMs/SeaLLMs-v3-1.5B-Chat-GGUF"
MODEL_FILENAME = "SeaLLMs-v3-1.5B-Chat.q4_k_m.gguf"
MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")

def download_seallm():
    print(f"Downloading {MODEL_FILENAME} (approx. 1 GB)...")
    print("This is a highly optimized 4-bit model that runs blazingly fast on CPU RAM.")
    
    os.makedirs(MODELS_DIR, exist_ok=True)
    
    try:
        # Download the model to Hugging Face cache and get the path
        model_path = hf_hub_download(
            repo_id=MODEL_REPO,
            filename=MODEL_FILENAME,
            cache_dir=MODELS_DIR
        )
        
        # Symlink or move it to models dir for easier access
        dest_path = os.path.join(MODELS_DIR, "SeaLLMs-v3-1.5B-Chat.Q4_K_M.gguf")
        
        if os.path.exists(dest_path):
            os.remove(dest_path)
            
        try:
            os.symlink(model_path, dest_path)
        except OSError:
            import shutil
            shutil.copy2(model_path, dest_path)
            
        print(f"\n✅ Download complete! Model saved to:\n{dest_path}")
        print("You can now run VIDA Studio Pro with fully local Khmer AI.")
        
    except Exception as e:
        print(f"Failed to download model: {e}")

if __name__ == "__main__":
    download_seallm()
