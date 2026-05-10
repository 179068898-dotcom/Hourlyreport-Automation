@echo off
setlocal
title hourly_report_bot - menu
cd /d "%~dp0"

echo ==========================================
echo hourly_report_bot - menu
echo ==========================================
echo Current folder:
echo %CD%
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv was not found.
  echo Please run install_env.bat first.
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" menu.py
echo.
echo Menu closed.
pause
