@echo off
rem Read-only audit of NoLlama + Qwen readiness (no auto-fix).
cd /d "%~dp0\..\.."

if "%NOLLAMA_HOME%"=="" set NOLLAMA_HOME=C:\Users\Rudol\NoLlama
if "%HERMES_CHAT_MODEL%"=="" set HERMES_CHAT_MODEL=qwen3-14b-int4

python -u scripts\run_intel_gpu\nollama_setup.py --check %*
exit /b %ERRORLEVEL%
