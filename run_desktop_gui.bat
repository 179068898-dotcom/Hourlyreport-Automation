@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Baidu Data Automation Console
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0" || exit /b 1

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] First launch: preparing the runtime environment...
  call "%~dp0install_env.bat"
  if errorlevel 1 (
    echo [ERROR] Runtime environment setup failed.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  echo [INFO] Installing the desktop interface...
  ".venv\Scripts\python.exe" -m pip install PySide6 --disable-pip-version-check
  if errorlevel 1 (
    echo [ERROR] Desktop interface installation failed.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -m gui.app
exit /b %ERRORLEVEL%
