@echo off
setlocal
cd /d "%~dp0\..\.."
set HERMES_WORKSPACE_ROOTS=%CD%
echo === HERMES Trading Test Run ===
echo Seed: pipeline_state.test_trading.seed.json
echo Output: generated\simple_rsi_strategy\ (wiped from loop state on live completion)
echo.
if "%1"=="live" (
  set HERMES_DRY_RUN=
  set HERMES_SKIP_CURSOR=
  python "main orchestration loop\orchestrator\main.py" --seed "main orchestration loop\pipeline_state.test_trading.seed.json"
) else (
  set HERMES_DRY_RUN=1
  set HERMES_SKIP_CURSOR=1
  python "main orchestration loop\orchestrator\main.py" --seed "main orchestration loop\pipeline_state.test_trading.seed.json" --dry-run
)
exit /b %ERRORLEVEL%
