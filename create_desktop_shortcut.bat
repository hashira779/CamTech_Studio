@echo off
setlocal
title Create VIDA Desktop Shortcut

set "BASE_DIR=%~dp0"
set "TARGET_BAT=%BASE_DIR%run_vida_desktop.bat"
set "ICON_PATH=%BASE_DIR%VidaStudio.WinUI\Assets\AppIcon.ico"

echo ================================================================
echo    Creating Desktop Shortcut for VIDA Studio
echo ================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell; " ^
    "$DesktopPath = [Environment]::GetFolderPath('Desktop'); " ^
    "$ShortcutPath = Join-Path $DesktopPath 'VIDA Studio.lnk'; " ^
    "$Shortcut = $WshShell.CreateShortcut($ShortcutPath); " ^
    "$Shortcut.TargetPath = '%TARGET_BAT%'; " ^
    "$Shortcut.WorkingDirectory = '%BASE_DIR%'; " ^
    "if (Test-Path '%ICON_PATH%') { $Shortcut.IconLocation = '%ICON_PATH%,0' }; " ^
    "$Shortcut.Description = 'Launch VIDA - Visual Intelligent Dynamic Audio-Video Studio'; " ^
    "$Shortcut.Save(); " ^
    "Write-Host '[SUCCESS] Desktop shortcut created at:' $ShortcutPath -ForegroundColor Green"

echo.
pause
