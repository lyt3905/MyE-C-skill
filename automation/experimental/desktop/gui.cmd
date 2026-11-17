@echo off
setlocal
set "MYEC_GUI_PYTHON=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%MYEC_GUI_PYTHON%" (
  echo Python environment missing. See README.md for installation.
  pause
  exit /b 2
)
start "MyE-C Automation" "%MYEC_GUI_PYTHON%" -m mye_c_automation ui %*
