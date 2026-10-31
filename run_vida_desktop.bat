@echo off
title VIDA - Visual Intelligent Dynamic Audio-Video Studio [Backend Service]
color 0B

echo ================================================================
echo    VIDA - Visual Intelligent Dynamic Audio-Video Studio
echo             Web Studio ^& Native Desktop App Edition
echo ================================================================
echo.

set BASE_DIR=%~dp0
cd /d "%BASE_DIR%"

set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=4
set PYTHONUNBUFFERED=1

set PYTHON_EXE=%BASE_DIR%venv\Scripts\python.exe

:: Check if venv python exists and actually runs
set REBUILD_VENV=0
if not exist "%PYTHON_EXE%" set REBUILD_VENV=1
if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -c "import sys" >nul 2>&1
    if errorlevel 1 set REBUILD_VENV=1
)

if "%REBUILD_VENV%"=="1" (
    echo [*] Python environment is missing or invalid. Setting up with Python 3.14...
    if exist "C:\Python314\python.exe" (
        "C:\Python314\python.exe" -m venv "%BASE_DIR%venv"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
        "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" -m venv "%BASE_DIR%venv"
    ) else (
        py -3.14 -m venv "%BASE_DIR%venv"
    )
    call "%BASE_DIR%venv\Scripts\pip.exe" install -r "%BASE_DIR%backend\requirements.txt"
    set PYTHON_EXE=%BASE_DIR%venv\Scripts\python.exe
)

echo [*] Launching VIDA Backend Service ^& Desktop App...
start "VIDA Backend Service" "%PYTHON_EXE%" tools\desktop_app.py
exit
