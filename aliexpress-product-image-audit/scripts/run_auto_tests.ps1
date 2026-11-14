param([string]$Python = '')
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
$Log = Join-Path $RepoRoot 'reports\auto-v1-current-regression.log'
$Writer = [System.IO.StreamWriter]::new($Log, $false, [System.Text.UTF8Encoding]::new($false))
try {
    $env:PYTHONPATH = Join-Path $RepoRoot 'scripts'
    & $Python -m unittest discover -s tests -v 2>&1 | ForEach-Object {
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
