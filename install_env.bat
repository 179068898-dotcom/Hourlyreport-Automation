@echo off
setlocal EnableExtensions DisableDelayedExpansion
title hourly_report_bot - install environment
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
cd /d "%~dp0" || goto :root_failed

echo [ENV][1/5] Checking Python...
set "PYTHON_EXE="
set "PYTHON_ARGS="
set "USING_EXISTING_VENV="

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" --version >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
    set "USING_EXISTING_VENV=1"
  )
)
if not defined PYTHON_EXE if exist "runtime\python-3.14.5\python.exe" set "PYTHON_EXE=%CD%\runtime\python-3.14.5\python.exe"

if /i "%~1"=="--check" goto :check_only

if not defined PYTHON_EXE (
  echo [ENV][2/5] Python was not found. Downloading the private runtime...
  powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap_python.ps1"
  if errorlevel 1 goto :python_failed
  set "PYTHON_EXE=%CD%\runtime\python-3.14.5\python.exe"
)

echo [ENV][2/5] Python: %PYTHON_EXE% %PYTHON_ARGS%
"%PYTHON_EXE%" %PYTHON_ARGS% --version
if errorlevel 1 goto :python_failed

if defined USING_EXISTING_VENV (
  echo [ENV][3/5] Existing project environment found.
) else (
  echo [ENV][3/5] Creating the project environment...
  "%PYTHON_EXE%" %PYTHON_ARGS% -m venv .venv
  if errorlevel 1 goto :venv_failed
)

echo [ENV][4/5] Installing runtime dependencies. The first setup may take a few minutes...
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check
if errorlevel 1 goto :dependency_failed
set "RUNTIME_REQUIREMENTS=%~dp0requirements-runtime.txt"
if exist "%~dp0requirements-runtime.lock.txt" set "RUNTIME_REQUIREMENTS=%~dp0requirements-runtime.lock.txt"
".venv\Scripts\python.exe" -m pip install -r "%RUNTIME_REQUIREMENTS%" --disable-pip-version-check
if errorlevel 1 goto :dependency_failed

echo [ENV][5/5] Environment setup completed.
exit /b 0

:check_only
if not defined PYTHON_EXE (
  echo [ENV][CHECK] PYTHON_NOT_FOUND
  exit /b 3
)
echo [ENV][CHECK] PYTHON_READY=%PYTHON_EXE% %PYTHON_ARGS%
"%PYTHON_EXE%" %PYTHON_ARGS% --version
if errorlevel 1 exit /b 1
exit /b 0

:root_failed
echo [ERROR] Cannot open the application folder.
goto :failed

:python_failed
echo [ERROR] Python setup failed. Check the network or Python installation and retry.
goto :failed

:venv_failed
echo [ERROR] Failed to create .venv.
goto :failed

:dependency_failed
echo [ERROR] Failed to install runtime dependencies. Check the network and retry.

:failed
if not "%HURLY_REPORT_BOT_AUTO_INSTALL%"=="1" pause
exit /b 1
