@echo off
setlocal
cd /d "%~dp0\..\.."
echo === HERMES Auto Runtime (Windows) ===
echo T09=cursor with auto: local bridge then cloud if git remote exists
echo.
set HERMES_T09_RUNTIME=cursor
set HERMES_CURSOR_RUNTIME=auto
set HERMES_DRY_RUN=
set HERMES_SKIP_CURSOR=
if "%1"=="dry" (
  set HERMES_DRY_RUN=1
  set HERMES_SKIP_CURSOR=1
  python "main orchestration loop\orchestrator\main.py" --seed "main orchestration loop\pipeline_state.test_trading.seed.json" --dry-run
) else (
  python "main orchestration loop\orchestrator\main.py" --seed "main orchestration loop\pipeline_state.test_trading.seed.json"
)
exit /b %ERRORLEVEL%
