@echo off
setlocal EnableExtensions DisableDelayedExpansion
title hourly_report_bot - menu
cd /d "%~dp0" || exit /b 1

echo ==========================================
echo hourly_report_bot - menu
echo ==========================================
echo Current folder:
echo %CD%
echo.

set "NEED_INSTALL="
if not exist ".venv\Scripts\python.exe" (
  set "NEED_INSTALL=1"
)

if not defined NEED_INSTALL (
  ".venv\Scripts\python.exe" -c "import openpyxl, pandas, xlrd, dateutil, playwright, rich" >nul 2>nul
  if errorlevel 1 set "NEED_INSTALL=1"
)

if defined NEED_INSTALL (
  echo Python environment is missing or incomplete. Installing dependencies...
  call "%~dp0install_env.bat"
  if errorlevel 1 (
    echo [ERROR] Environment installation failed. Menu cannot start.
    echo.
    pause
    exit /b 1
  )
  echo.
)

".venv\Scripts\python.exe" menu.py
echo.
echo Menu closed.
pause
