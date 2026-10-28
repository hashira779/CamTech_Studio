"""
Converts the word aligner (torchaudio MMS_FA) to ONNX, so VIDA can align lyrics without torch.

torch needs about 4 GB of free memory to align a song and crashes when it is short of it.
The ONNX model gives the same results on onnxruntime, without torch.

Writes, into models/:
  mms_fa.onnx         the model (float32, 1.26 GB)
  mms_fa_vocab.json   letter -> output index, as torchaudio's bundle.get_dict(star=None)

Only the core Wav2Vec2 model is exported; the wrapper's waveform layer-norm and log-softmax
are done in numpy by backend/onnx_aligner.py.
Usage: python tools/export_aligner_onnx.py   (needs ~4 GB free memory, once)
"""
import gc
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "models")


def main() -> int:
    import torch
    import torchaudio

    os.makedirs(OUT, exist_ok=True)
    fp32 = os.path.join(OUT, "mms_fa.onnx")

    bundle = torchaudio.pipelines.MMS_FA
    with open(os.path.join(OUT, "mms_fa_vocab.json"), "w", encoding="utf-8") as f:
        json.dump(bundle.get_dict(star=None), f, ensure_ascii=False)

    if not os.path.exists(fp32):
        wrapped = bundle.get_model(with_star=False, dl_kwargs={"weights_only": True, "map_location": "cpu"})
        core = wrapped.model.eval()
        del wrapped
        gc.collect()
        dummy = torch.zeros(1, 16000 * 4)
        with torch.no_grad():
            torch.onnx.export(
                core, (dummy,), fp32,
                input_names=["audio"], output_names=["logits"],
                dynamic_axes={"audio": {1: "samples"}, "logits": {1: "frames"}},
                opset_version=17, do_constant_folding=True,
            )
        del core
        gc.collect()
        print(f"wrote {fp32} ({os.path.getsize(fp32) / 1e9:.2f} GB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
