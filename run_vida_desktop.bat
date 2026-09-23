@echo off
title VIDA — Visual Intelligent Dynamic Audio-Video Studio
color 0B

echo ================================================================
echo    VIDA — Visual Intelligent Dynamic Audio-Video Studio
echo             Web Studio ^& Native Edge App Edition
echo ================================================================
echo.

cd /d "%~dp0"
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

if not exist "venv\Scripts\python.exe" (
    echo [*] Setting up Python environment...
    py -3.12 -m venv venv
    call venv\Scripts\pip install -r backend\requirements.txt
)

echo [*] Launching VIDA Desktop Studio...
start "" venv\Scripts\python.exe desktop_app.py

exit
