@echo off
setlocal
cd /d "%~dp0\..\.."
echo === HERMES Live NN Cursor Stress Test (WSL) ===
wsl -d Ubuntu-24.04 -u root -- env HERMES_RESUME=0 bash "main orchestration loop/run/11_run_live_nn_cursor.sh"
exit /b %ERRORLEVEL%
