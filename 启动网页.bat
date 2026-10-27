@echo off
chcp 65001 >nul
title 网易云歌单整理器
cd /d "%~dp0"
if not exist "%~dp0runtime\python\python.exe" (
  echo [缺少 runtime] 这个仓库没有内置运行环境。
  echo 请从 Releases 下载便携包，或在项目目录运行：python tools\build_portable.py
  pause
  exit /b 1
)
echo 正在启动，浏览器会自动打开 http://127.0.0.1:8765/
echo 关闭本窗口即可停止服务。
echo.
"%~dp0runtime\python\python.exe" -m netease_sorter serve %*
pause
