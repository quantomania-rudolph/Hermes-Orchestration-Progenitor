@echo off
rem Step 4: Verify all models and install artifacts are on disk (no downloads).
cd /d "%~dp0\..\.."

if "%NOLLAMA_HOME%"=="" set NOLLAMA_HOME=C:\Users\Rudol\NoLlama
if "%HERMES_CHAT_MODEL%"=="" set HERMES_CHAT_MODEL=qwen3-14b-int4

python -u scripts\install_models\verify_models_installed.py %*
set EXIT=%ERRORLEVEL%
if not "%EXIT%"=="0" pause
exit /b %EXIT%
