@echo off
setlocal
cd /d "%~dp0\..\.."
echo === HERMES Cloud Agent Trading Test ===
echo Requires: git remote origin + pushed main branch (run 07_setup_git_cloud.bat first)
echo.
if not exist ".git" (
  echo [FAIL] No .git — run 07_setup_git_cloud.bat
  exit /b 1
)
git remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo [FAIL] No origin remote — run 07_setup_git_cloud.bat
  exit /b 1
)
set HERMES_T09_RUNTIME=cursor
set HERMES_CURSOR_RUNTIME=cloud
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
