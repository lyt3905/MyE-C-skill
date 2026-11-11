# -*- coding: utf-8 -*-
<#
    weibo-cdp-login.ps1  —  一键启动带 CDP 的独立 Edge 「登录窗口」，供 weibo-figure-intel 自动续期微博 SUB。

    作用（= 旧版桌面 weibo-cdp-login.bat 的增强版）：
      1. 用【独立 profile】C:\Users\shana\EdgeWeibo 启动 Edge，开远程调试端口 9222，
         并打开 https://weibo.com 。不碰你日常 Edge 的 profile 和登录态。
      2. 若该 profile 上次登录过微博，会直接复用登录态；没登录就手动登一次。
      3. 等你登录完成后（脚本会轮询 CDP 直到抓到有效 SUB），自动调用
         cdp_get_sub.py grab --write 把 SUB 写回 scripts\wb_cookie.json，并做登录校验。
      4. 想关窗口时，用 -Stop 参数或直接关 Edge 窗口即可。

    用法（PowerShell）：
      # 打开登录窗口并等待写回 cookie（最常用）
      pwsh -File scripts\weibo-cdp-login.ps1

      # 只想手动打开窗口、不自动抓（登完自己再跑 grab）
      pwsh -File scripts\weibo-cdp-login.ps1 -NoGrab

      # 只探测 9222 是否已可用，不做任何启动
      pwsh -File scripts\weibo-cdp-login.ps1 -ProbeOnly

      # 清理：按命令行精确终止 EdgeWeibo 的调试实例（不影响日常 Edge）
      pwsh -File scripts\weibo-cdp-login.ps1 -Stop

    说明：
      - 必须用独立 user-data-dir。Edge/Chrome 136+ 禁止在默认 profile 上开远程调试（端口会静默不开）。
      - 端口只监听 127.0.0.1，用完建议关掉窗口。
      - 本脚本调用的 cdp_get_sub.py 已内建 ProxyHandler({}) 绕代理，这里探测也一并绕代理。
#>

param(
    [int]$Port = 9222,
    [string]$ProfileDir = "C:\Users\shana\EdgeWeibo",
    [switch]$NoGrab,
    [switch]$ProbeOnly,
    [switch]$Stop,
    [int]$WaitSeconds = 180
)

$ErrorActionPreference = "Stop"

# —— 把控制台切到 UTF-8，避免中文乱码 ——
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillDir  = Split-Path -Parent $ScriptDir

# 优先用管理版 Python，其次 PATH 里的 python
$PyCandidates = @(
    "C:\Users\shana\.dsh\dsh-runtimes\dsh-next-primary-runtime\dependencies\python\python.exe",
    "C:\Users\shana\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
)
$Python = $null
foreach ($p in $PyCandidates) { if (Test-Path $p) { $Python = $p; break } }
if (-not $Python) { $Python = "python" }

$EdgeExe = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

$env:HTTP_PROXY  = ""
$env:HTTPS_PROXY = ""
$env:NO_PROXY    = "127.0.0.1,localhost"

function Test-Cdp {
    param([int]$P)
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$P/json/version" -TimeoutSec 3 -UseBasicParsing
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

function Stop-EdgeWeibo {
    param([string]$Prof)
    $procs = Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
             Where-Object { $_.CommandLine -and $_.CommandLine -like "*$Prof*" }
    if ($procs) {
        $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 2
        $left = (Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
                 Where-Object { $_.CommandLine -and $_.CommandLine -like "*$Prof*" }).Count
        Write-Host "已清理 EdgeWeibo 实例，剩余进程数：$left" -ForegroundColor Yellow
    } else {
        Write-Host "没有在跑的 EdgeWeibo 实例。" -ForegroundColor Gray
    }
}

# ---------------- -Stop ----------------
if ($Stop) { Stop-EdgeWeibo -Prof $ProfileDir; exit 0 }

# ---------------- -ProbeOnly ----------------
if ($ProbeOnly) {
    if (Test-Cdp -P $Port) {
        Write-Host "✅ 端口 $Port 的 CDP 已可用。" -ForegroundColor Green
        exit 0
    } else {
        Write-Host "❌ 端口 $Port 未开（需要先运行本脚本不带 -ProbeOnly 启动登录窗口）。" -ForegroundColor Red
        exit 2
    }
}

if (-not $EdgeExe) {
    Write-Host "❌ 找不到 Edge / Chrome 可执行文件，无法启动登录窗口。" -ForegroundColor Red
    exit 3
}

# ---------------- 启动登录窗口 ----------------
if (Test-Cdp -P $Port) {
    Write-Host "ℹ️ 端口 $Port 已在监听，复用现有实例（未重复启动）。" -ForegroundColor Cyan
} else {
    Write-Host "▶ 启动独立 profile 的 Edge（$ProfileDir），调试端口 $Port ..." -ForegroundColor Cyan
    if (-not (Test-Path $ProfileDir)) {
        New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
        Write-Host "  （已创建新 profile 目录，首次需要在这个窗口里登录一次微博）" -ForegroundColor Gray
    }
    Start-Process -FilePath $EdgeExe -ArgumentList @(
        "--user-data-dir=`"$ProfileDir`"",
        "--remote-debugging-port=$Port",
        "--no-first-run",
        "https://weibo.com"
    )
    # 等端口起来
    $ok = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Cdp -P $Port) { $ok = $true; break }
    }
    if (-not $ok) {
        Write-Host "❌ 30 秒内调试端口仍未开。可能 Edge 版本过旧/被策略禁用了远程调试。" -ForegroundColor Red
        exit 4
    }
    Write-Host "✅ 调试端口已就绪。" -ForegroundColor Green
}

Write-Host ""
Write-Host "👉 请在刚打开的 Edge 窗口里登录 weibo.com（若已登录会自动续期）。" -ForegroundColor Yellow
Write-Host "   本脚本会轮询等待登录态，抓到有效 SUB 后自动写回 wb_cookie.json ..." -ForegroundColor Yellow

if ($NoGrab) {
    Write-Host "（-NoGrab：不自动抓取。登完请自行运行：$Python scripts\cdp_get_sub.py grab --port $Port --write）" -ForegroundColor Gray
    exit 0
}

# ---------------- 轮询 grab --write 直到成功 ----------------
$Deadline = (Get-Date).AddSeconds($WaitSeconds)
$Success  = $false
while ((Get-Date) -lt $Deadline) {
    $out = & $Python "$ScriptDir\cdp_get_sub.py" grab --port $Port --write 2>&1
    $txt = ($out | Out-String)
    if ($txt -match "成功获取 SUB" -and $txt -match "已写回") {
        Write-Host ""
        Write-Host "✅ 登录完成，SUB 已写回 wb_cookie.json。" -ForegroundColor Green
        Write-Host $txt.Trim()
        $Success = $true
        break
    } elseif ($txt -match "未登录|没有 SUB|未通过校验") {
        # 还没登录/登录态无效，继续等
        Write-Host "  …尚未检测到有效登录，$(([int]($Deadline - (Get-Date)).TotalSeconds)) 秒后重试" -ForegroundColor DarkGray
    } else {
        Write-Host "  …抓取未成功，稍后重试（$($txt.Trim().Split("`n")[-1])）" -ForegroundColor DarkGray
    }
    Start-Sleep -Seconds 6
}

if (-not $Success) {
    Write-Host ""
    Write-Host "⚠️ $WaitSeconds 秒内未抓到有效 SUB。" -ForegroundColor Red
    Write-Host "   请确认已在窗口里登录微博，然后手动重试：" -ForegroundColor Yellow
    Write-Host "   $Python `"$ScriptDir\cdp_get_sub.py`" grab --port $Port --write" -ForegroundColor Yellow
    Write-Host "   完成后建议运行本脚本 -Stop 关闭该 Edge 实例。" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "提示：本次只是取了 cookie，Edge 窗口还开着。用完可运行：" -ForegroundColor Cyan
Write-Host "   pwsh -File `"$PSCommandPath`" -Stop" -ForegroundColor Cyan
exit 0
