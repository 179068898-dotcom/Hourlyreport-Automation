@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d D:\自动化脚本\hourly_report_bot_release_v0.4.4

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv was not found. Run install_env.bat first.
  exit /b 1
)

.venv\Scripts\python.exe main.py --mode preflight --task daily
if errorlevel 1 (
  echo [ERROR] Preflight failed. Daily run stopped.
  exit /b 1
)

if "%~1"=="" (
  .venv\Scripts\python.exe main.py --mode run-daily --yes
) else (
  .venv\Scripts\python.exe main.py --mode run-daily --date "%~1" --yes
)
exit /b %ERRORLEVEL%
