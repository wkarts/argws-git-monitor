@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
if errorlevel 1 (
  echo.
  echo A instalacao encontrou um erro. Consulte a mensagem acima.
  pause
  exit /b 1
)
pause
