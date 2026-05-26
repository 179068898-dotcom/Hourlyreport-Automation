@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d D:\自动化脚本\hourly_report_bot_release_v0.4.4

if "%~1"=="" (
  echo Usage: run_openclaw_hourly.bat 11点 ^| 15点 ^| 18点
  exit /b 2
)

set "PERIOD=%~1"
if not "%PERIOD%"=="11点" if not "%PERIOD%"=="15点" if not "%PERIOD%"=="18点" (
  echo [ERROR] Unsupported period: %PERIOD%
  echo Usage: run_openclaw_hourly.bat 11点 ^| 15点 ^| 18点
  exit /b 2
)

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv was not found. Run install_env.bat first.
  exit /b 1
)

.venv\Scripts\python.exe main.py --mode preflight
if errorlevel 1 (
  echo [ERROR] Preflight failed. Hourly run stopped.
  exit /b 1
)

.venv\Scripts\python.exe main.py --mode run --period "%PERIOD%" --yes
exit /b %ERRORLEVEL%
