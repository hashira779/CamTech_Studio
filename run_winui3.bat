@echo off
chcp 65001 > nul
title VIDA Studio - Modern Windows 11 WinUI 3 + C#/.NET 10
color 0B

echo ================================================================
echo    VIDA - Visual Intelligent Dynamic Audio-Video Studio
echo       Windows 11 Native WinUI 3 + C#/.NET 10 Edition
echo ================================================================
echo.

set BASE_DIR=%~dp0
set DOTNET_ROOT=D:\dotnet
set PATH=D:\dotnet;%PATH%

set BIN_DIR=%BASE_DIR%VidaStudio.WinUI\bin\Release\net10.0-windows10.0.26100.0\win-x64
if not exist "%BIN_DIR%\VidaStudio.exe" (
    set BIN_DIR=%BASE_DIR%VidaStudio.WinUI\bin\Debug\net10.0-windows10.0.26100.0\win-x64
)

if not exist "%BIN_DIR%\VidaStudio.exe" (
    echo [*] Building Self-Contained WinUI 3 Desktop App for .NET 10...
    cd /d "%BASE_DIR%VidaStudio.WinUI"
    D:\dotnet\dotnet.exe build VidaStudio.csproj -c Release -r win-x64
    set BIN_DIR=%BASE_DIR%VidaStudio.WinUI\bin\Release\net10.0-windows10.0.26100.0\win-x64
)

set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=4
set HF_HUB_OFFLINE=1

set PYTHON_EXE=%BASE_DIR%venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

echo [*] Starting Python Backend Server (Running Minimized with venv)...
start "VIDA Backend Server" /MIN cmd /c "cd /d %BASE_DIR% && ""%PYTHON_EXE%"" -m uvicorn backend.app:app"

echo [*] Launching 100%% Native Windows 11 WinUI 3 App...
cd /d "%BIN_DIR%"
start "" "VidaStudio.exe"
exit
