@echo off
:: ════════════════════════════════════════════════════════════
::  Khmer ASR Pipeline — One-Click Install (Windows)
::  Ryzen 4000 / CPU-only build
:: ════════════════════════════════════════════════════════════
setlocal

echo.
echo  Installing Khmer Singing Lyrics Pipeline
echo  ==========================================

:: Use the VIDA venv if it exists, otherwise assume system Python
set PYTHON=%~dp0..\venv\Scripts\python.exe
if not exist "%PYTHON%" (
    echo  VIDA venv not found — using system Python
    set PYTHON=python
)
echo  Using Python: %PYTHON%
echo.

:: Step 1 — Upgrade pip
echo [1/5] Upgrading pip...
"%PYTHON%" -m pip install --upgrade pip --quiet
if errorlevel 1 goto :error

:: Step 2 — Install PyTorch CPU-only FIRST (must come before demucs)
:: This avoids downloading the 2.5 GB CUDA build
echo [2/5] Installing PyTorch (CPU-only build)...
echo       This may take a few minutes on first run.
"%PYTHON%" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --quiet
if errorlevel 1 goto :error

:: Step 3 — Install faster-whisper and audio dependencies
echo [3/5] Installing faster-whisper, soundfile, imageio-ffmpeg...
"%PYTHON%" -m pip install "faster-whisper>=1.2.1" "soundfile>=0.12.0" "imageio-ffmpeg>=0.4.9" --quiet
if errorlevel 1 goto :error

:: Step 4 — Install Demucs (requires torch from Step 2)
echo [4/5] Installing Demucs vocal separator...
"%PYTHON%" -m pip install "demucs>=4.0.0" --quiet
if errorlevel 1 goto :error

:: Step 5 — Install evaluation tools
echo [5/5] Installing jiwer (CER/WER evaluation)...
"%PYTHON%" -m pip install "jiwer>=3.0.0" --quiet
if errorlevel 1 goto :error

echo.
echo  ✅ Installation complete!
echo.
echo  Quick test (transcription only, no GPU needed):
echo    cd khmer_asr
echo    %PYTHON% pipeline.py --input ..\uploads\demo_khmer_song.wav --skip-separation --model tiny
echo.
goto :end

:error
echo.
echo  ❌ Installation failed. Check the error above.
echo.
exit /b 1

:end
endlocal
