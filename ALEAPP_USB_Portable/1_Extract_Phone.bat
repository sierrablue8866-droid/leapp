@echo off
setlocal enabledelayedexpansion
title Samsung A56 Forensic Extractor (Portable Suite)
cd /d "%~dp0"

echo ==========================================================
echo       ALEAPP Portable USB Forensic Suite
echo ==========================================================
echo.

if exist "%~dp0usb_forensic_extract.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0usb_forensic_extract.ps1"
    goto END
)

set ADB=platform-tools\adb.exe
if not exist "%ADB%" (
    echo [ERROR] platform-tools\adb.exe not found!
    pause
    exit /b 1
)

:CHECK_DEVICE
echo Checking for connected phone via ADB...
"%ADB%" devices -l
echo.

"%ADB%" get-state 1>nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [!] Phone not yet authorized or disconnected.
    echo Press any key to re-check, or close this window to exit.
    pause >nul
    cls
    goto CHECK_DEVICE
)

echo [OK] Phone detected and authorized!
set OUT_DIR=%~dp0extracted_phone_data
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

echo Extracting artifacts to %OUT_DIR% ...
"%ADB%" pull /sdcard/DCIM "%OUT_DIR%\DCIM"
"%ADB%" pull /sdcard/Pictures "%OUT_DIR%\Pictures"
"%ADB%" pull /sdcard/Download "%OUT_DIR%\Download"
"%ADB%" pull /sdcard/Documents "%OUT_DIR%\Documents"
"%ADB%" pull /sdcard/Android/media "%OUT_DIR%\media"
"%ADB%" shell dumpsys package > "%OUT_DIR%\dumpsys_packages.txt" 2>nul
"%ADB%" shell logcat -d > "%OUT_DIR%\logcat.txt" 2>nul

if exist "%~dp0aleappGUI.exe" (
    start "" "%~dp0aleappGUI.exe"
)

:END
pause
