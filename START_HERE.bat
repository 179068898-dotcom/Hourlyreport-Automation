@echo off
setlocal EnableExtensions DisableDelayedExpansion
title hourly_report_bot - START HERE
cd /d "%~dp0" || exit /b 1

echo ==========================================
echo hourly_report_bot - START HERE
echo ==========================================
echo Current folder:
echo %CD%
echo.
echo This window should stay open.
echo If you see errors, take a screenshot and send it back.
echo.

if not exist ".venv\Scripts\python.exe" (
  echo First run detected: installing environment...
  call "%~dp0install_env.bat"
  if errorlevel 1 (
    echo.
    echo [ERROR] Environment installation failed.
    pause
    exit /b 1
  )
)

echo Opening menu...
call "%~dp0run_menu.bat"
pause
