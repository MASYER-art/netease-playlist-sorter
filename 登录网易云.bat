@echo off
chcp 65001 >nul
title 登录网易云
cd /d "%~dp0"
echo 会打开一个专用 Edge 窗口，请用网易云 App 扫码登录。
echo 登录成功后窗口会自动关闭。
echo.
"%~dp0runtime\python\python.exe" -m netease_sorter login --from-edge %*
pause
