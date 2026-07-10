@echo off
cd /d "%~dp0\..\.."
if "%NOLLAMA_HOME%"=="" set NOLLAMA_HOME=C:\Users\Rudol\NoLlama
if "%HERMES_CHAT_MODEL%"=="" set HERMES_CHAT_MODEL=qwen3-14b-int4
python -u scripts\run_intel_gpu\test_nollama_integration.py %*
exit /b %ERRORLEVEL%
