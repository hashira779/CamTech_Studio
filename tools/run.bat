@echo off
title VIDA - Visual Intelligent Dynamic Audio-Video Studio [Backend Service]
color 0B

echo ================================================================
echo             VIDA Video Automation Studio Launcher
echo ================================================================
echo.

set BASE_DIR=%~dp0..\
cd /d "%BASE_DIR%"

set PYTHON_EXE=%BASE_DIR%venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" (
    echo [!] Virtual environment not found. Setting up Python environment...
    py -3.12 -m venv venv
    call venv\Scripts\pip install -r backend\requirements.txt
    set PYTHON_EXE=%BASE_DIR%venv\Scripts\python.exe
)

echo [*] Launching VIDA Studio Desktop App...
start "VIDA Backend Service" "%PYTHON_EXE%" tools\desktop_app.py
exit
