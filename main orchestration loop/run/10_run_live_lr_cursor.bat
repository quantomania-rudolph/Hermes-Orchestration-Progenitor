@echo off
setlocal
cd /d "%~dp0\..\.."
echo === HERMES Live LR Cursor Test (WSL) ===
echo Requires: NoLlama on Windows + WSL Cursor SDK (09_verify_wsl_cursor.bat)
echo Log: main orchestration loop\state\live_lr_cursor.log
echo.
curl.exe -fsS --max-time 5 http://127.0.0.1:8000/v1/models >nul 2>&1
if errorlevel 1 (
  echo [WARN] NoLlama not responding on :8000 — start scripts\run_intel_gpu\01_start_nollama.bat
)
wsl -d Ubuntu-24.04 -u root -- env HERMES_RESUME=0 bash "main orchestration loop/run/10_run_live_lr_cursor.sh"
set RC=%ERRORLEVEL%
if %RC%==0 (
  python "main orchestration loop\verification\verify_live_cursor_audit.py"
  set RC=%ERRORLEVEL%
)
exit /b %RC%
