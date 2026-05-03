@echo off
title RouteManager

:: 檢查是否具管理員權限，沒有就自動重啟要求 UAC
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
python route_manager.py
pause
