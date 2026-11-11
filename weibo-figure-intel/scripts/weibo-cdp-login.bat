@echo off
REM ============================================================
REM  weibo-cdp-login.bat — 一键启动「带 CDP 调试端口的独立 Edge 登录窗口」，
REM  供 weibo-figure-intel 自动续期微博 SUB cookie。
REM
REM  这是旧版桌面 bat 的 skill 内置增强版：除了开窗口，还会自动
REM  等待登录并写回 scripts\wb_cookie.json（真正省掉手抄 SUB）。
REM
REM  用法：
REM    - 双击本文件        → 打开登录窗口 + 自动抓取写回 cookie
REM    - 只想开窗口不抓     → 在命令行跑  weibo-cdp-login.bat -NoGrab
REM    - 只探测端口         → weibo-cdp-login.bat -ProbeOnly
REM    - 关掉该调试实例     → weibo-cdp-login.bat -Stop
REM
REM  说明：用的是独立 profile 目录 C:\Users\shana\EdgeWeibo，
REM  不碰你日常 Edge 的 profile / 登录。端口 9222 只监听 127.0.0.1。
REM ============================================================
setlocal
set "PS1=%~dp0weibo-cdp-login.ps1"
pwsh -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
if errorlevel 1 (
  echo.
  echo [提示] 若系统没有 pwsh，可改用： powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
  pause
)
endlocal
