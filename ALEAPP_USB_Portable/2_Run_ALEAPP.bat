@echo off
cd /d "%~dp0"
title ALEAPP - Portable Edition
echo ==========================================================
echo Starting Portable ALEAPP...
echo (No Python installation required)
echo ==========================================================

if not exist "aleappGUI.exe" (
    echo [ERROR] aleappGUI.exe not found!
    pause
    exit /b 1
)

start "" "%~dp0aleappGUI.exe"
