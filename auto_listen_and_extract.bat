@echo off
setlocal enabledelayedexpansion
title ALEAPP Auto Extractor & Parser
cd /d "%~dp0"

set ADB=platform-tools\adb.exe
if not exist "%ADB%" set ADB=H:\leapp\platform-tools\adb.exe

echo ==========================================================
echo       ALEAPP Automatic Detection, Extraction & Parsing
echo ==========================================================
echo.
echo Waiting for your phone to connect and authorize...
echo.
echo Look at your phone screen:
echo   - Unlock your phone.
echo   - Turn ON Settings -^> Developer options -^> USB debugging.
echo   - Tap 'ALLOW' on the popup prompt.
echo.

:WAIT_LOOP
"%ADB%" wait-for-device
echo [OK] Phone authorized!

set OUT_DIR=H:\extracted_phone_data
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

echo.
echo Extracting forensic artifacts from phone to %OUT_DIR% ...
echo 1/4 Extracting Downloads...
"%ADB%" pull /sdcard/Download "%OUT_DIR%\Download"
echo 2/4 Extracting DCIM (Photos/Videos)...
"%ADB%" pull /sdcard/DCIM "%OUT_DIR%\DCIM"
echo 3/4 Extracting Documents...
"%ADB%" pull /sdcard/Documents "%OUT_DIR%\Documents"
echo 4/4 Extracting App Data...
"%ADB%" pull /sdcard/Android/media "%OUT_DIR%\media"

echo.
echo ==========================================================
echo Extraction complete! Launching ALEAPP Parser now...
echo ==========================================================

set REPORT_DIR=H:\reports
if not exist "%REPORT_DIR%" mkdir "%REPORT_DIR%"

if exist "ALEAPP\.venv\Scripts\python.exe" (
    start "" "ALEAPP\.venv\Scripts\python.exe" "ALEAPP\aleappGUI.py"
) else if exist "ALEAPP_USB_Portable\aleappGUI.exe" (
    start "" "ALEAPP_USB_Portable\aleappGUI.exe"
)

echo ALEAPP GUI opened.
echo Select Input Path: %OUT_DIR%
echo Select Output Path: %REPORT_DIR%
pause
