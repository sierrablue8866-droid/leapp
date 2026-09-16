@echo off
setfacl enabledelayedexpansion
title Android Phone USB Extractor

set ADB=H:\leapp\platform-tools\adb.exe
if not exist "%ADB%" set ADB=%~dp0platform-tools\adb.exe
if not exist "%ADB%" set ADB=adb.exe

echo ==========================================================
echo        Android Phone USB Detection & Extractor
echo ==========================================================
echo.

:CHECK_DEVICE
echo Checking for connected Android phone via ADB...
"%ADB%" devices
echo.

"%ADB%" get-state 1>nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [!] No authorized Android phone detected.
    echo.
    echo Please make sure:
    echo  1. USB cable is firmly connected to this PC.
    echo  2. On your phone: Go to Settings -^> About Phone -^> tap 'Build Number' 7 times.
    echo  3. Go to Settings -^> Developer Options -^> Enable 'USB Debugging'.
    echo  4. Unlock your phone and look at the screen:
    echo     TAP 'ALLOW' on the popup: 'Allow USB debugging from this computer?'
    echo.
    echo Press any key to re-check, or close this window to exit.
    pause >nul
    cls
    goto CHECK_DEVICE
)

echo [OK] Android device detected and authorized!
echo.
set OUT_DIR=H:\extracted_phone_data
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

echo Where would you like to save extracted files?
echo Default: %OUT_DIR%
echo.
echo Select extraction type:
echo  [1] Common forensic folders (Downloads, DCIM/Photos, Documents, WhatsApp)
echo  [2] Full Internal Storage (/sdcard/)
echo  [3] Create Full ADB Backup (.ab file)
echo  [4] Open Interactive Phone Shell
echo.
set /p CHOICE="Enter choice (1-4): "

if "%CHOICE%"=="1" (
    echo.
    echo Extracting Download folder...
    "%ADB%" pull /sdcard/Download "%OUT_DIR%\Download"
    echo Extracting DCIM (Photos)...
    "%ADB%" pull /sdcard/DCIM "%OUT_DIR%\DCIM"
    echo Extracting Pictures...
    "%ADB%" pull /sdcard/Pictures "%OUT_DIR%\Pictures"
    echo Extracting Documents...
    "%ADB%" pull /sdcard/Documents "%OUT_DIR%\Documents"
    echo Extracting WhatsApp media (if present)...
    "%ADB%" pull /sdcard/Android/media/com.whatsapp "%OUT_DIR%\WhatsApp"
    echo.
    echo Extraction complete! Files saved to: %OUT_DIR%
)

if "%CHOICE%"=="2" (
    echo.
    echo Extracting entire /sdcard/ storage to %OUT_DIR%\sdcard ...
    "%ADB%" pull /sdcard/ "%OUT_DIR%\sdcard"
    echo.
    echo Full storage extraction complete! Files saved to: %OUT_DIR%\sdcard
)

if "%CHOICE%"=="3" (
    echo.
    echo Initiating full device backup to %OUT_DIR%\backup.ab ...
    echo LOOK AT YOUR PHONE SCREEN and tap 'BACK UP MY DATA' to confirm!
    "%ADB%" backup -all -f "%OUT_DIR%\backup.ab"
    echo.
    echo Backup complete! File saved to: %OUT_DIR%\backup.ab
)

if "%CHOICE%"=="4" (
    echo.
    echo Opening phone shell (type 'exit' to quit)...
    "%ADB%" shell
)

echo.
echo ==========================================================
echo You can now open ALEAPP and select "%OUT_DIR%" as your Input Path!
echo ==========================================================
pause
