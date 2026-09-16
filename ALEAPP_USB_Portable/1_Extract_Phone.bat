@echo off
setlocal enabledelayedexpansion
title Android Phone USB Extractor
cd /d "%~dp0"

set ADB=platform-tools\adb.exe
if not exist "%ADB%" (
    echo [ERROR] platform-tools\adb.exe not found!
    pause
    exit /b 1
)

echo ==========================================================
echo       Android Mobile USB Detection & Extractor
echo ==========================================================
echo.

:CHECK_DEVICE
echo Scanning for connected Android phone...
"%ADB%" devices
echo.

"%ADB%" get-state 1>nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [!] No authorized Android phone detected.
    echo.
    echo Please follow these steps on your phone:
    echo  1. Connect USB cable firmly to this computer.
    echo  2. Go to: Settings -^> About Phone -^> tap 'Build Number' 7 times.
    echo  3. Go to: Settings -^> Developer Options -^> Enable 'USB Debugging'.
    echo  4. Unlock your phone and look at the screen:
    echo     TAP 'ALLOW' on the popup: 'Allow USB debugging from this computer?'
    echo.
    echo Press any key to re-check, or close this window to exit.
    pause >nul
    cls
    goto CHECK_DEVICE
)

echo [OK] Phone connected and authorized!
echo.
set OUT_DIR=%~dp0extracted_phone_data
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

echo Extraction destination: %OUT_DIR%
echo.
echo Select what to extract:
echo  [1] Key forensic folders (Downloads, Photos/DCIM, Documents, WhatsApp)
echo  [2] Full Internal Storage (/sdcard/)
echo  [3] Create Full Device ADB Backup (.ab archive)
echo  [4] Open Interactive Phone Shell
echo.
set /p CHOICE="Enter choice (1-4): "

if "%CHOICE%"=="1" (
    echo.
    echo Extracting Downloads...
    "%ADB%" pull /sdcard/Download "%OUT_DIR%\Download"
    echo Extracting DCIM (Photos & Videos)...
    "%ADB%" pull /sdcard/DCIM "%OUT_DIR%\DCIM"
    echo Extracting Pictures...
    "%ADB%" pull /sdcard/Pictures "%OUT_DIR%\Pictures"
    echo Extracting Documents...
    "%ADB%" pull /sdcard/Documents "%OUT_DIR%\Documents"
    echo Extracting WhatsApp (if present)...
    "%ADB%" pull /sdcard/Android/media/com.whatsapp "%OUT_DIR%\WhatsApp"
    echo.
    echo [DONE] Extraction complete! Files saved to: %OUT_DIR%
)

if "%CHOICE%"=="2" (
    echo.
    echo Extracting all internal storage (/sdcard/) to %OUT_DIR%\sdcard ...
    "%ADB%" pull /sdcard/ "%OUT_DIR%\sdcard"
    echo.
    echo [DONE] Full storage extracted to: %OUT_DIR%\sdcard
)

if "%CHOICE%"=="3" (
    echo.
    echo Creating ADB backup to %OUT_DIR%\backup.ab ...
    echo [IMPORTANT] Check your phone screen now and tap 'Back up my data'!
    "%ADB%" backup -all -f "%OUT_DIR%\backup.ab"
    echo.
    echo [DONE] Backup saved to: %OUT_DIR%\backup.ab
)

if "%CHOICE%"=="4" (
    echo.
    echo Opening phone shell (type 'exit' to quit)...
    "%ADB%" shell
)

echo.
echo ==========================================================
echo Now run '2_Run_ALEAPP.bat' and select:
echo Input Path: %OUT_DIR%
echo ==========================================================
pause
