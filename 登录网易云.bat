@echo off
chcp 65001 >nul
title 登录网易云
cd /d "%~dp0"
if not exist "%~dp0runtime\python\python.exe" (
  echo [缺少 runtime] 这个仓库没有内置运行环境。
  echo 请从 Releases 下载便携包，或在项目目录运行：python tools\build_portable.py
  pause
  exit /b 1
)
echo 会打开一个专用 Edge 窗口，请用网易云 App 扫码登录。
echo 登录成功后窗口会自动关闭。
echo.
"%~dp0runtime\python\python.exe" -m netease_sorter login --from-edge %*
pause
