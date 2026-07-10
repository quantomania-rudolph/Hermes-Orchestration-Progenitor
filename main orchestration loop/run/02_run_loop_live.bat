@echo off
setlocal
cd /d "%~dp0\..\.."
python -c "from hermes_secrets import cursor_key_configured; import sys; sys.exit(0 if cursor_key_configured() else 1)" >nul 2>&1
if errorlevel 1 (
  echo [WARN] CURSOR_API_KEY not set — copy .env.example to .env.local and add your key.
) else (
  echo [OK] CURSOR_API_KEY loaded from .env.local
)
echo === HERMES Main Loop (LIVE) ===
call "main orchestration loop\run\00_preflight.bat"
if errorlevel 1 exit /b 1
python "main orchestration loop\orchestrator\main.py"
exit /b %ERRORLEVEL%
