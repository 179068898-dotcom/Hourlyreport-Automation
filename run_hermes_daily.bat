@echo off
setlocal EnableExtensions DisableDelayedExpansion
title HERMES Daily - fixed entry - 20260710
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "HURLY_REPORT_BOT_AUTO_INSTALL=1"
cd /d "%~dp0" || exit /b 1

echo [HERMES][20260710] Daily fixed entry. Do not bypass this BAT.
echo [HERMES] Working directory: %CD%

if not exist ".venv\Scripts\python.exe" (
  echo [HERMES] Runtime is missing. Running automatic environment setup...
  call "%~dp0install_env.bat"
  if errorlevel 1 (
    echo [ERROR] Automatic environment setup failed.
    exit /b 1
  )
)

echo [HERMES] Running daily quick preflight...
.venv\Scripts\python.exe main.py --mode preflight --task daily --quick
if errorlevel 1 (
  echo [ERROR] Preflight failed. Daily run stopped.
  exit /b 1
)

if "%~1"=="" (
  echo [HERMES] Running daily for default date: yesterday.
  .venv\Scripts\python.exe main.py --mode run-daily --yes
) else (
  echo [HERMES] Running daily for date: %~1
  .venv\Scripts\python.exe main.py --mode run-daily --date "%~1" --yes
)
exit /b %ERRORLEVEL%
