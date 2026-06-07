@echo off
setlocal
title OpenClaw Daily - fixed entry
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

echo [OpenClaw] Daily fixed entry. Do not bypass this BAT.
echo [OpenClaw] Working directory: %CD%

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv was not found. Run install_env.bat first.
  exit /b 1
)

echo [OpenClaw] Running daily quick preflight...
.venv\Scripts\python.exe main.py --mode preflight --task daily --quick
if errorlevel 1 (
  echo [ERROR] Preflight failed. Daily run stopped.
  exit /b 1
)

if "%~1"=="" (
  echo [OpenClaw] Running daily for default date: yesterday.
  .venv\Scripts\python.exe main.py --mode run-daily --yes
) else (
  echo [OpenClaw] Running daily for date: %~1
  .venv\Scripts\python.exe main.py --mode run-daily --date "%~1" --yes
)
exit /b %ERRORLEVEL%
