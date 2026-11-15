"""
Unit tests for UVR5 (Ultimate Vocal Remover) integration into VIDA.
"""
import os
import pytest
from backend import uvr_separator

def test_uvr_engines_defined():
    engines = uvr_separator.UVR_ENGINES
    assert "uvr_kim_vocal_2" in engines
    assert "uvr_voc_ft" in engines
    assert "uvr_de_reverb" in engines
    assert engines["uvr_kim_vocal_2"]["model_file"] == "Kim_Vocal_2.onnx"

def test_uvr_ffmpeg_environment():
    uvr_separator._ensure_ffmpeg_path()
    path = os.environ.get("PATH", "")
    assert len(path) > 0
