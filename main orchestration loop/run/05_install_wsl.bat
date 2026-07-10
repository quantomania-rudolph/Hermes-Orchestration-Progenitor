@echo off
setlocal
echo === HERMES WSL2 Setup ===
echo.
wsl --status >nul 2>&1
if %ERRORLEVEL%==0 (
  echo [OK] WSL already installed.
  wsl -l -v
  goto :done
)
echo WSL2 is not installed. This requires Administrator + a reboot.
echo.
echo Option A - run this script as Administrator:
echo   Right-click 05_install_wsl.bat ^> Run as administrator
echo.
echo Option B - PowerShell as Admin:
echo   wsl --install
echo   wsl --set-default-version 2
echo.
choice /C YN /M "Try elevated WSL install now (UAC prompt)"
if errorlevel 2 goto :manual
powershell -Command "Start-Process wsl -ArgumentList '--install','-d','Ubuntu' -Verb RunAs -Wait"
echo.
echo If install started, reboot Windows then run 05_run_wsl.bat
goto :done
:manual
echo Skipped auto-install. Run manually: wsl --install
:done
echo.
echo After WSL+Ubuntu are ready:
echo   main orchestration loop\run\05_run_wsl.bat
exit /b 0
