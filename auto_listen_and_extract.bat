@echo off
setlocal enabledelayedexpansion
title Samsung A56 Forensic Extractor & ALEAPP Parser
cd /d "%~dp0"

set ADB=platform-tools\adb.exe
if not exist "%ADB%" set ADB=H:\leapp\platform-tools\adb.exe

echo ==========================================================
echo       Samsung A56 Forensic Extractor & ALEAPP Parser
echo ==========================================================
echo.
echo Checking USB status for Samsung A56...
echo.

:WAIT_DEVICE
echo Waiting for Samsung A56 to connect via USB with USB Debugging enabled...
echo.
echo [!] If the phone is plugged in but not detected:
echo   1. Check your USB cable (must support data transfer, not charging only).
echo   2. On Samsung A56: Settings -^> Security and privacy -^> Auto Blocker -^> Turn OFF.
echo   3. On Samsung A56: Settings -^> Developer options -^> Turn ON 'USB debugging'.
echo   4. UNLOCK your phone and tap 'ALLOW' on the popup prompt.
echo.

"%ADB%" wait-for-device

echo [OK] Device connected! Checking authorization status...
"%ADB%" get-state 1>nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [!] Device is detected but UNAUTHORIZED.
    echo Please unlock your phone screen now and tap 'ALLOW' on the USB Debugging prompt.
    timeout /t 3 /nobreak >nul
    goto WAIT_DEVICE
)

echo.
echo ==========================================================
echo [SUCCESS] Samsung A56 Authorized!
echo ==========================================================
for /f "tokens=*" %%a in ('"%ADB%" shell getprop ro.product.model 2^>nul') do echo Model: %%a
for /f "tokens=*" %%a in ('"%ADB%" shell getprop ro.build.version.release 2^>nul') do echo Android Version: %%a
for /f "tokens=*" %%a in ('"%ADB%" shell getprop ro.serialno 2^>nul') do echo Serial Number: %%a
echo ==========================================================
echo.

set OUT_DIR=H:\extracted_phone_data
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

echo [1/7] Pulling DCIM (Photos, Camera, Screenshots)...
"%ADB%" pull /sdcard/DCIM "%OUT_DIR%\DCIM"

echo [2/7] Pulling Pictures...
"%ADB%" pull /sdcard/Pictures "%OUT_DIR%\Pictures"

echo [3/7] Pulling Downloads...
"%ADB%" pull /sdcard/Download "%OUT_DIR%\Download"

echo [4/7] Pulling Documents...
"%ADB%" pull /sdcard/Documents "%OUT_DIR%\Documents"

echo [5/7] Pulling Android App Media (WhatsApp, Telegram, etc.)...
"%ADB%" pull /sdcard/Android/media "%OUT_DIR%\media"

echo [6/7] Dumping Android System Telemetry & Logs...
"%ADB%" shell dumpsys package > "%OUT_DIR%\dumpsys_packages.txt" 2>nul
"%ADB%" shell dumpsys netstats > "%OUT_DIR%\dumpsys_netstats.txt" 2>nul
"%ADB%" shell dumpsys batterystats > "%OUT_DIR%\dumpsys_batterystats.txt" 2>nul
"%ADB%" shell pm list packages -f > "%OUT_DIR%\installed_packages.txt" 2>nul
"%ADB%" shell logcat -d > "%OUT_DIR%\logcat.txt" 2>nul

echo [7/7] Launching ALEAPP Forensic Parser...
set REPORT_DIR=H:\reports
if not exist "%REPORT_DIR%" mkdir "%REPORT_DIR%"

if exist "ALEAPP\.venv\Scripts\python.exe" (
    start "" "ALEAPP\.venv\Scripts\python.exe" "ALEAPP\aleappGUI.py"
) else if exist "ALEAPP_USB_Portable\aleappGUI.exe" (
    start "" "ALEAPP_USB_Portable\aleappGUI.exe"
)

echo.
echo ==========================================================
echo Extraction completed to: %OUT_DIR%
echo ALEAPP GUI opened! Select '%OUT_DIR%' as Input folder.
echo ==========================================================
echo.
pause
