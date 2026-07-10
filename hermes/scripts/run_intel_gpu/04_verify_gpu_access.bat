@echo off
rem Verify Qwen3-14B is running and routed to Intel Arc GPU (chat probe + X-Device header).
cd /d "%~dp0\..\.."

if "%NOLLAMA_HOME%"=="" set NOLLAMA_HOME=C:\Users\Rudol\NoLlama
if "%HERMES_CHAT_MODEL%"=="" set HERMES_CHAT_MODEL=qwen3-14b-int4

echo === Verify Qwen14B Intel GPU access ===
echo     This runs a live chat probe (30-120s on first load).
echo.

call "%~dp0check_nollama_health.bat"
if errorlevel 1 (
    echo [error] NoLlama not running. Run 01_start_nollama.bat first.
    pause
    exit /b 1
)

python -u scripts\run_intel_gpu\test_nollama_integration.py %*
set EXIT=%ERRORLEVEL%
if not "%EXIT%"=="0" pause
exit /b %EXIT%
