@echo off
chcp 65001 >nul
title 网易云歌单整理器
cd /d "%~dp0"
echo 正在启动，浏览器会自动打开 http://127.0.0.1:8765/
echo 关闭本窗口即可停止服务。
echo.
"%~dp0runtime\python\python.exe" -m netease_sorter serve %*
pause
