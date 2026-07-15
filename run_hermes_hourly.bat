@echo off
setlocal EnableExtensions DisableDelayedExpansion
title HERMES Hourly - fixed entry - 20260710
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "HURLY_REPORT_BOT_AUTO_INSTALL=1"
cd /d "%~dp0" || exit /b 1

echo [HERMES][20260710] Hourly fixed entry. Do not bypass this BAT.
echo [HERMES] Working directory: %CD%

if "%~1"=="" (
  echo Usage: run_hermes_hourly.bat ^<period^>
  echo Accepted periods are validated by the application.
  exit /b 2
)
set "PERIOD=%~1"

if not exist ".venv\Scripts\python.exe" (
  echo [HERMES] Runtime is missing. Running automatic environment setup...
  call "%~dp0install_env.bat"
  if errorlevel 1 (
    echo [ERROR] Automatic environment setup failed.
    exit /b 1
  )
)

echo [HERMES] Running hourly quick preflight...
.venv\Scripts\python.exe main.py --mode preflight --quick
if errorlevel 1 (
  echo [ERROR] Preflight failed. Hourly run stopped.
  exit /b 1
)

echo [HERMES] Running hourly period: %PERIOD%
.venv\Scripts\python.exe main.py --mode run --period "%PERIOD%" --yes
exit /b %ERRORLEVEL%
