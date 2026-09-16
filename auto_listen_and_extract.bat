@echo off
setlocal enabledelayedexpansion
title ALEAPP Ultimate USB Forensic Extractor
cd /d "%~dp0"

echo ==========================================================
echo       ALEAPP Ultimate USB Forensic Extractor
echo ==========================================================
echo Launching enhanced USB Forensic Suite...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0usb_forensic_extract.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] PowerShell launcher exited. Falling back to ADB direct listener...
    echo.
    set ADB=platform-tools\adb.exe
    if not exist "%ADB%" set ADB=H:\leapp\platform-tools\adb.exe
    "%ADB%" wait-for-device
    "%ADB%" devices -l
)

pause
