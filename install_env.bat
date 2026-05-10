@echo off
setlocal
title hourly_report_bot - install env
cd /d "%~dp0"

echo ==========================================
echo hourly_report_bot - install environment
echo ==========================================
echo Current folder:
echo %CD%
echo.

set "PY_CMD="
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3"

if "%PY_CMD%"=="" (
  python --version >nul 2>nul
  if not errorlevel 1 set "PY_CMD=python"
)

if "%PY_CMD%"=="" (
  echo [ERROR] Python was not found.
  echo Please install Python 3.10+ first, then run this file again.
  echo Download: https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

echo Python command: %PY_CMD%
%PY_CMD% --version
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY_CMD% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create .venv.
    pause
    exit /b 1
  )
) else (
  echo Virtual environment already exists.
)

echo.
echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] Failed to upgrade pip.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Failed to install requirements.
  pause
  exit /b 1
)

echo.
echo Installation finished.
echo Next step: run run_menu.bat
echo.
pause
