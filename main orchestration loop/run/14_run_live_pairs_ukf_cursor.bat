@echo off
setlocal
cd /d "%~dp0\..\.."
wsl -l -v 2>nul | findstr /i "Ubuntu" >nul
if errorlevel 1 (
  echo [FAIL] Ubuntu WSL not ready. Run main orchestration loop\run\05_setup_wsl_environment.bat
  exit /b 1
)
wsl --set-default Ubuntu-24.04 >nul 2>&1
set HERMES_RESUME=1
set HERMES_USE_INTEL_XPU=auto
echo === HERMES Live Pairs UKF via WSL2 Cursor ===
wsl -d Ubuntu-24.04 -- bash "main orchestration loop/run/14_run_live_pairs_ukf_cursor.sh"
exit /b %ERRORLEVEL%
