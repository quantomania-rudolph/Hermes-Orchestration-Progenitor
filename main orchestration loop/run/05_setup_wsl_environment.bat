@echo off
setlocal
cd /d "%~dp0\..\.."
wsl -l -v 2>nul | findstr /i "Ubuntu" >nul
if errorlevel 1 (
  echo [FAIL] No Ubuntu WSL distro. Run:
  echo   winget install Canonical.Ubuntu.2404
  echo   ubuntu2404.exe install --root
  exit /b 1
)
echo === HERMES WSL Environment Setup ===
echo Distro: Ubuntu-24.04 (WSL2)
echo.
wsl --set-default Ubuntu-24.04 >nul 2>&1
wsl -d Ubuntu-24.04 -u root -- bash "main orchestration loop/run/05_setup_wsl_environment.sh"
exit /b %ERRORLEVEL%
