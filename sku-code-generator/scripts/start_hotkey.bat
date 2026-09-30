@echo off
rem Ctrl+B hotkey launcher. Keep this file ASCII-only.
chcp 65001 > nul
title Ctrl+B - next code
set PY=C:\Users\shana\.workbuddy\binaries\python\versions\3.13.12\python.exe
"%PY%" "%~dp0sku_hotkey.py" %*
echo.
echo [hotkey exited] Press any key to close this window.
pause > nul
