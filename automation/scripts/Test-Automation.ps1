param([string]$Python = '', [string]$Output = '')
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
if (-not $Python) { $Python = Join-Path $project '.venv/Scripts/python.exe' }
if (-not $Output) { $Output = Join-Path $project 'reports/current-regression' }
if (-not (Test-Path -LiteralPath $Python)) { throw 'Install the independent Python environment first; see README.md.' }
& $Python -B (Join-Path $PSScriptRoot 'run_tests.py') --output $Output
exit $LASTEXITCODE
