@echo off
setlocal
title RouteManager

rem Check for administrator privileges; relaunch elevated if needed.
net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Requesting administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

set "PYTHON_CMD="

rem Check for Python in common installation locations (bypass Windows Store aliases)
if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
    set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
    goto :found_python
)

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    goto :found_python
)

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :found_python
)

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :found_python
)

rem Try py launcher
where py >nul 2>&1
if not errorlevel 1 (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3"
        goto :found_python
    )
)

rem Try python commands (may hit Windows Store aliases)
where python >nul 2>&1
if not errorlevel 1 (
    python --version >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
        goto :found_python
    )
)

rem Python not found
echo Python 3 was not found.
echo Install Python 3 from https://www.python.org/downloads/windows/
echo During installation, enable "Add python.exe to PATH".
echo.
echo If Microsoft Store aliases are getting in the way, disable:
echo Settings ^> Apps ^> Advanced app settings ^> App execution aliases ^> python.exe / python3.exe
pause
exit /b 1

:found_python

%PYTHON_CMD% "%~dp0route_manager.py"
pause
