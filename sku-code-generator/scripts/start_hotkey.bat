@echo off
rem SKU hotkey launcher (Ctrl+B). Keep this file ASCII-only.
chcp 65001 > nul
title SKU Hotkey - Ctrl+B
set PY=C:\Users\shana\.workbuddy\binaries\python\versions\3.13.12\python.exe
"%PY%" "%~dp0sku_hotkey.py" %*
echo.
echo [SKU hotkey exited] Press any key to close this window.
pause > nul
