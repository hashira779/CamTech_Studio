@echo off
title VIDA — Video Automation Studio
color 0B

echo ================================================================
echo             VIDA Video Automation Studio Launcher
echo ================================================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [!] Virtual environment not found. Setting up Python environment...
    py -3.12 -m venv venv
    call venv\Scripts\pip install -r backend\requirements.txt
)

echo [*] Launching VIDA Studio Desktop App...
start "" venv\Scripts\python.exe desktop_app.py

exit
