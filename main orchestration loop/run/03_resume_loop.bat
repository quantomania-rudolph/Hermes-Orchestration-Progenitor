@echo off
setlocal
cd /d "%~dp0\..\.."
set HERMES_DRY_RUN=1
set HERMES_SKIP_CURSOR=1
python "main orchestration loop\orchestrator\main.py" --dry-run --resume
exit /b %ERRORLEVEL%
