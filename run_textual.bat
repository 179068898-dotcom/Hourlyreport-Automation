@echo off
setlocal
title 百度竞价自动化工作台
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d D:\自动化脚本\hourly_report_bot_release_v0.4.4

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] 未找到 .venv，请先运行 install_env.bat 安装依赖。
  exit /b 1
)

.venv\Scripts\python.exe textual_app.py
exit /b %ERRORLEVEL%
