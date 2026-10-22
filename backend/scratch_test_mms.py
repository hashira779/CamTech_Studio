import torch
import torchaudio
import numpy as np

print("PyTorch:", torch.__version__)
print("Torchaudio:", torchaudio.__version__)
print("CUDA:", torch.cuda.is_available())

bundle = torchaudio.pipelines.MMS_FA
model = bundle.get_model(with_star=False, dl_kwargs={'weights_only': True, 'map_location': 'cpu'})
model.eval()

x = torch.randn(1, 16000 * 5)
with torch.inference_mode():
    em, _ = model(x)
print("Forward pass OK, shape:", em.shape)
