@echo off
rem Offline-safe daily setup: free ports, start NoLlama, warmup Qwen14B (no downloads).
cd /d "%~dp0\..\.."

if "%NOLLAMA_HOME%"=="" set NOLLAMA_HOME=C:\Users\Rudol\NoLlama
if "%HERMES_CHAT_MODEL%"=="" set HERMES_CHAT_MODEL=qwen3-14b-int4

echo === Daily Intel GPU setup (local fix + warmup) ===
echo     Pass --install or --pip only when internet is stable.
python -u scripts\run_intel_gpu\nollama_setup.py --warmup %*
set EXIT=%ERRORLEVEL%
if not "%EXIT%"=="0" pause
exit /b %EXIT%
