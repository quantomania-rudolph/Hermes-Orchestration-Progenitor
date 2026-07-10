@echo off
rem Start NoLlama on Intel GPU at port 8010 (Windows orchestrator default).
setlocal EnableDelayedExpansion
cd /d "%~dp0"

if "%NOLLAMA_HOME%"=="" set NOLLAMA_HOME=C:\Users\Rudol\NoLlama
if not exist "%NOLLAMA_HOME%\nollama.py" (
    echo [error] NoLlama not installed at %NOLLAMA_HOME%
    exit /b 1
)

call 00_stop_nollama.bat nopause
if errorlevel 1 exit /b 1

echo [start] Launching NoLlama GPU on port 8010...
start "NoLlama-8010" cmd /k "cd /d %NOLLAMA_HOME% && venv\Scripts\python.exe nollama.py --device GPU --port 8010"

echo Waiting for http://127.0.0.1:8010/health (up to 120s)...
set /a WAIT=0
:wait_health
timeout /t 3 /nobreak >nul
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:8010/health' -UseBasicParsing -TimeoutSec 5).StatusCode } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto :health_up
set /a WAIT+=3
if !WAIT! geq 120 (
    echo [warn] Port 8010 health not ready after 120s
    exit /b 1
)
goto :wait_health

:health_up
echo [ok] NoLlama listening on http://127.0.0.1:8010
exit /b 0
