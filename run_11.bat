@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo .venv not found. Please run setup_env.bat first.
  pause
  exit /b 1
)
set "KST_FILE=%~1"
if "%KST_FILE%"=="" (
  ".venv\Scripts\python.exe" "main.py" --mode run --period 11
) else (
  ".venv\Scripts\python.exe" "main.py" --mode run --period 11 --file "%KST_FILE%"
)
pause
