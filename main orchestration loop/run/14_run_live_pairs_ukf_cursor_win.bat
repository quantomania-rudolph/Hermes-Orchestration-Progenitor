@echo off
rem Live HERMES pairs UKF: Windows orchestrator + WSL2 Cursor agent CLI + Intel Arc NoLlama/XPU.
setlocal EnableDelayedExpansion
cd /d "%~dp0\..\.."

set LOG=main orchestration loop\state\live_pairs_ukf_cursor.log
echo === HERMES Live Pairs UKF (Win orchestrator + WSL2 Cursor + Arc) === > "%LOG%"
echo Time: %DATE% %TIME% >> "%LOG%"

if "%NOLLAMA_PORT%"=="" set NOLLAMA_PORT=8010
if "%NOLLAMA_OPENAI_BASE_URL%"=="" set NOLLAMA_OPENAI_BASE_URL=http://127.0.0.1:%NOLLAMA_PORT%/v1
if "%NOLLAMA_HEALTH_URL%"=="" set NOLLAMA_HEALTH_URL=http://127.0.0.1:%NOLLAMA_PORT%/health

set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8
set HERMES_T09_RUNTIME=cursor
set HERMES_CURSOR_BACKEND=cli
set HERMES_CURSOR_AGENT_MODEL=auto
set HERMES_CURSOR_MODEL=auto
set HERMES_CURSOR_RUNTIME=local
set HERMES_REQUIRE_LIVE_CURSOR=1
set HERMES_USE_INTEL_XPU=1
set HERMES_OUTPUT_SLUG=pairs_regime_ukf_trader
set HERMES_RESEARCH_SMOKE=1
set HERMES_SKIP_INDEX_REBUILD=1
set HERMES_CURSOR_SESSION_TIMEOUT_SEC=1200
set HERMES_RESUME=1
set HERMES_CHAT_MODEL=qwen3-14b-int4

echo NoLlama: %NOLLAMA_HEALTH_URL% >> "%LOG%"
echo [env] HERMES_CURSOR_BACKEND=cli via WSL2 agent >> "%LOG%"

wsl -d Ubuntu-24.04 -- bash "main orchestration loop/run/_wsl_agent_probe.sh" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [FAIL] WSL Cursor agent CLI preflight >> "%LOG%"
  exit /b 1
)

python -c "from hermes_live_stack import enforce_hermes_live_stack; enforce_hermes_live_stack(); print('[OK] Live stack: WSL2 Cursor + NoLlama Arc + XPU')" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 1

set MAIN_ARGS=--seed "main orchestration loop/pipeline_state.pairs_regime_ukf_trader.seed.json" --repo "%CD%"
if exist "main orchestration loop\pipeline_state.json" set MAIN_ARGS=%MAIN_ARGS% --resume

python "main orchestration loop/orchestrator/main.py" %MAIN_ARGS% >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo [exit] orchestrator rc=%RC% >> "%LOG%"
exit /b %RC%
