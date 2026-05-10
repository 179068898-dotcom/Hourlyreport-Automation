@echo off
chcp 65001 >nul
cd /d %~dp0
if exist config.json (
  echo config.json 已存在，不覆盖。
) else (
  copy config.example.json config.json >nul
  echo 已从 config.example.json 创建 config.json，请修改 excel_path 后再运行。
)
pause
