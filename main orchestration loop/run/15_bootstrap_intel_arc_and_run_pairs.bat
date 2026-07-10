@echo off
rem Kill stale listeners, start NoLlama on Intel Arc, launch live HERMES pairs run via WSL2 Cursor.
setlocal EnableDelayedExpansion
cd /d "%~dp0\..\.."

echo === Bootstrap Intel Arc + Live HERMES Pairs UKF ===

echo [1/5] Stopping HERMES Python processes...
for /f "tokens=2" %%p in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| findstr /I "PID:"') do taskkill /F /PID %%p >nul 2>&1

echo [2/5] Freeing NoLlama ports...
call "%~dp0..\..\scripts\run_intel_gpu\00_stop_nollama.bat" nopause

echo [3/5] Starting NoLlama on Intel Arc GPU port 8010...
set NOLLAMA_PORT=8010
set NOLLAMA_OPENAI_BASE_URL=http://127.0.0.1:8010/v1
set NOLLAMA_HEALTH_URL=http://127.0.0.1:8010/health
set HERMES_CURSOR_AGENT_MODEL=auto
set HERMES_CURSOR_MODEL=auto

if "%NOLLAMA_HOME%"=="" set NOLLAMA_HOME=C:\Users\Rudol\NoLlama
echo [4/5] Launching NoLlama on port !NOLLAMA_PORT!...
start "NoLlama-Arc" /MIN cmd /c "cd /d %NOLLAMA_HOME% && .\venv\Scripts\python.exe nollama.py --device GPU --port !NOLLAMA_PORT!"

set /a WAIT=0
:wait_nollama
timeout /t 3 /nobreak >nul
curl -sf --max-time 3 http://127.0.0.1:!NOLLAMA_PORT!/health | findstr /I "ready" >nul 2>&1
if not errorlevel 1 goto :nollama_up
set /a WAIT+=3
if !WAIT! geq 120 (
  echo [FAIL] NoLlama not ready after 120s on port !NOLLAMA_PORT!
  exit /b 1
)
goto :wait_nollama

:nollama_up
echo [ok] NoLlama ready on Intel Arc port !NOLLAMA_PORT!
set NOLLAMA_OPENAI_BASE_URL=http://127.0.0.1:!NOLLAMA_PORT!/v1
set NOLLAMA_HEALTH_URL=http://127.0.0.1:!NOLLAMA_PORT!/health
set HERMES_USE_INTEL_XPU=1
set HERMES_RESUME=1

echo [5/5] Launching live HERMES (Windows orchestrator + WSL2 Cursor)...
call "%~dp014_run_live_pairs_ukf_cursor_win.bat"
exit /b %ERRORLEVEL%
