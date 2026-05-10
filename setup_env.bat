@echo off
chcp 65001 >nul
cd /d %~dp0

set PYTHON_EXE=C:\Users\1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe

if not exist "%PYTHON_EXE%" (
  echo Codex bundled Python not found: %PYTHON_EXE%
  echo Please install system Python or create .venv manually.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  "%PYTHON_EXE%" -m venv .venv
  if errorlevel 1 exit /b 1
)

.venv\Scripts\python.exe -m pip install --upgrade pip -i https://pypi.org/simple
if errorlevel 1 exit /b 1

.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.org/simple
if errorlevel 1 exit /b 1

echo Environment setup complete.
pause
