@echo off
rem Daily Hermes boot: NoLlama health, restart if dead, warmup, preflight.
cd /d "%~dp0\..\.."
set RUN_GPU=%~dp0
if "%HERMES_CHAT_MODEL%"=="" set HERMES_CHAT_MODEL=qwen3-14b-int4

echo === Hermes daily startup ===

call "%RUN_GPU%check_nollama_health.bat"
if errorlevel 1 (
    echo [fix] NoLlama down - restarting...
    call "%RUN_GPU%01_restart_nollama.bat"
    if errorlevel 1 (
        echo [FAIL] Could not start NoLlama.
        pause & exit /b 1
    )
) else (
    echo [OK] NoLlama health responding
)

python ensure_hermes_model.py --check >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Chat model missing.
    pause & exit /b 1
)

call "%RUN_GPU%02_warmup_qwen14b.bat"
if errorlevel 1 pause & exit /b 1

python hermes_preflight.py --quick --skip-cursor
echo.
echo Ready: python hermes_orchestrator.py "your task"
pause
