@echo off
title VIDA - Visual Intelligent Dynamic Audio-Video Studio [Backend Service]
color 0B

echo ================================================================
echo    VIDA - Visual Intelligent Dynamic Audio-Video Studio
echo             Web Studio ^& Native Edge App Edition
echo ================================================================
echo.

set BASE_DIR=%~dp0..\
cd /d "%BASE_DIR%"

set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=4
set HF_HUB_OFFLINE=1
set PYTHONUNBUFFERED=1

set PYTHON_EXE=%BASE_DIR%venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" (
    echo [*] Setting up Python environment...
    py -3.12 -m venv venv
    call venv\Scripts\pip install -r backend\requirements.txt
    set PYTHON_EXE=%BASE_DIR%venv\Scripts\python.exe
)

echo [*] Launching VIDA Backend Service ^& Desktop App...
start "VIDA Backend Service" "%PYTHON_EXE%" tools\desktop_app.py
exit
