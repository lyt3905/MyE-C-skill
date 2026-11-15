param([string]$Python = '', [string]$LogPath = '', [switch]$Offline, [string]$TestHarness = '')
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Python) {
    $LocalPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    $ExistingPython = Join-Path (Split-Path $RepoRoot -Parent) 'ae-img-audit\.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $LocalPython) { $Python = $LocalPython }
    elseif (Test-Path -LiteralPath $ExistingPython) { $Python = $ExistingPython }
    else { $Python = 'python' }
}
$PreviousPythonPath = $env:PYTHONPATH
$ExitCode = 1
Push-Location -LiteralPath $RepoRoot
$Log = if ($LogPath) { $LogPath } else { Join-Path $RepoRoot 'reports\auto-v1-current-regression.log' }
$Writer = [System.IO.StreamWriter]::new($Log, $false, [System.Text.UTF8Encoding]::new($false))
try {
    $env:PYTHONPATH = Join-Path $RepoRoot 'scripts'
    [string[]]$TestArgs = if ($TestHarness) { @($TestHarness) } elseif ($Offline) { @('-c', 'import socket,runpy; from unittest.mock import patch; deny=lambda *a,**k: (_ for _ in ()).throw(AssertionError("Network forbidden")); guards=[patch("urllib.request.urlopen",side_effect=deny),patch.object(socket.socket,"connect",side_effect=deny),patch.object(socket.socket,"connect_ex",side_effect=deny),patch("socket.create_connection",side_effect=deny)]; [g.start() for g in guards]; import sys; sys.argv=["unittest","discover","-s","tests","-v"]; runpy.run_module("unittest",run_name="__main__")') } else { @('-m','unittest','discover','-s','tests','-v') }
    & $Python @TestArgs 2>&1 | ForEach-Object {
        $Line = $_.ToString()
        $Writer.WriteLine($Line)
        Write-Output $Line
    }
    $ExitCode = $LASTEXITCODE
}
finally {
    $Writer.Dispose()
    $env:PYTHONPATH = $PreviousPythonPath
    Pop-Location
}
exit $ExitCode
