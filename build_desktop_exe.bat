@echo off
setlocal
title Build Desktop EXE
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv was not found. Run install_env.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -c "import PySide6, PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo Installing GUI build dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
  if errorlevel 1 (
    echo [ERROR] Failed to install GUI build dependencies.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" tools\build_desktop_exe.py
pause
exit /b %ERRORLEVEL%
