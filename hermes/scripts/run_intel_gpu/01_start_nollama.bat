@echo off
setlocal EnableDelayedExpansion
rem Start NoLlama on Intel GPU if not already running.
cd /d "%~dp0"

call check_nollama_health.bat
if not errorlevel 1 (
    echo [ok] NoLlama already running at http://127.0.0.1:8000
    exit /b 0
)

if "%NOLLAMA_HOME%"=="" set NOLLAMA_HOME=C:\Users\Rudol\NoLlama
if not exist "%NOLLAMA_HOME%\nollama.py" (
    echo [error] NoLlama not installed. Run scripts\install_models\00_install_everything.bat
    pause
    exit /b 1
)

if not exist "%NOLLAMA_HOME%\start.ps1" (
    echo [error] start.ps1 not found in NOLLAMA_HOME=%NOLLAMA_HOME%
    echo         Run scripts\install_models\02_download_qwen14b_intel_gpu.bat
    pause
    exit /b 1
)

echo [start] Launching NoLlama (Intel GPU) in a new window...
start "NoLlama" cmd /k "cd /d %NOLLAMA_HOME% && pwsh -NoProfile -ExecutionPolicy Bypass -File start.ps1"

echo Waiting for health endpoint (up to 90s)...
set /a WAIT=0
:wait_health
timeout /t 3 /nobreak >nul
call check_nollama_health.bat
if not errorlevel 1 goto :health_up
set /a WAIT+=3
if !WAIT! geq 90 (
    echo [warn] Health not ready after 90s. Check the NoLlama window for GPU errors.
    pause
    exit /b 1
)
goto :wait_health

:health_up
echo [ok] NoLlama health endpoint responding
exit /b 0
