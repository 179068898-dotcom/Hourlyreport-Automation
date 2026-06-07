@echo off
setlocal
title 百度日报小时报控制台
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [提示] 首次启动需要先安装运行环境。
  call "%~dp0install_env.bat"
  if errorlevel 1 (
    echo [错误] 运行环境安装失败。
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  echo [提示] 正在安装图形界面组件，请稍等...
  ".venv\Scripts\python.exe" -m pip install PySide6 pyinstaller
  if errorlevel 1 (
    echo [错误] 图形界面组件安装失败。
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -m gui.app
exit /b %ERRORLEVEL%
