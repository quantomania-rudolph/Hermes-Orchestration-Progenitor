@echo off
setlocal
cd /d "%~dp0\..\.."
echo === HERMES Live LSTM Optuna Vault Test (WSL) ===
echo Requires: NoLlama on Windows + WSL Cursor CLI (09_verify_wsl_cursor.bat)
echo Log: main orchestration loop\state\live_lstm_cursor.log
echo.
curl.exe -fsS --max-time 5 http://127.0.0.1:8000/v1/models >nul 2>&1
if errorlevel 1 (
  echo [WARN] NoLlama not responding on :8000 — start scripts\run_intel_gpu\01_start_nollama.bat
)
wsl -d Ubuntu-24.04 -u root -- env HERMES_RESUME=0 bash "main orchestration loop/run/12_run_live_lstm_cursor.sh"
set RC=%ERRORLEVEL%
if %RC%==0 (
  python "main orchestration loop\verification\verify_lstm_live_cursor.py"
  set RC=%ERRORLEVEL%
)
exit /b %RC%
