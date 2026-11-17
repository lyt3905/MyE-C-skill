@echo off
setlocal
set "MYEC_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%MYEC_PYTHON%" (
  echo Python environment missing. See README.md for installation.
  exit /b 2
)
if "%~1"=="" (
  "%MYEC_PYTHON%" -m mye_c_automation --help
) else (
  "%MYEC_PYTHON%" -m mye_c_automation %*
)
exit /b %errorlevel%
