@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo .venv not found. Please run setup_env.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "main.py" --mode parse-kst-export --period 15
pause
