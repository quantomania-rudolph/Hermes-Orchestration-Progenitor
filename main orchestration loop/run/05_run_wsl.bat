@echo off
setlocal
cd /d "%~dp0\..\.."
wsl --status >nul 2>&1
if errorlevel 1 (
  echo [FAIL] WSL not installed. Run: main orchestration loop\run\05_install_wsl.bat
  exit /b 1
)
set HERMES_T09_RUNTIME=cursor
set HERMES_CURSOR_RUNTIME=local
if "%1"=="live" (
  wsl bash "main orchestration loop/run/05_run_wsl.sh" live
) else (
  wsl bash "main orchestration loop/run/05_run_wsl.sh" dry
)
exit /b %ERRORLEVEL%
