@echo off
setlocal
title OpenClaw Hourly - fixed entry
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

echo [OpenClaw] Hourly fixed entry. Do not bypass this BAT.
echo [OpenClaw] Working directory: %CD%

if "%~1"=="" (
  echo Usage: run_openclaw_hourly.bat ^<period^>
  echo Period should be 11/15/18 with the required Chinese suffix used by this project.
  exit /b 2
)

set "PERIOD=%~1"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv was not found. Run install_env.bat first.
  exit /b 1
)

echo [OpenClaw] Running hourly quick preflight...
.venv\Scripts\python.exe main.py --mode preflight --quick
if errorlevel 1 (
  echo [ERROR] Preflight failed. Hourly run stopped.
  exit /b 1
)

echo [OpenClaw] Running hourly period: %PERIOD%
.venv\Scripts\python.exe main.py --mode run --period "%PERIOD%" --yes
exit /b %ERRORLEVEL%
