@echo off
setlocal EnableDelayedExpansion
rem Full Hermes startup: packages, NoLlama, warmup, index check, preflight.
cd /d "%~dp0\..\.."

set RUN_GPU=%~dp0
if "%HERMES_CHAT_MODEL%"=="" set HERMES_CHAT_MODEL=qwen3-14b-int4
set MODEL=%HERMES_CHAT_MODEL%
set FAIL=0

echo.
echo ============================================================
echo   HERMES STARTUP - connectivity checks
echo ============================================================
echo.

echo [1/7] Python packages...
python -c "import numpy, openai; from cursor_sdk import Agent; import sentence_transformers" >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Missing packages. Run: scripts\install_models\03_install_python_packages.bat
    set FAIL=1
    goto :summary
)
echo [OK] numpy, openai, cursor-sdk, sentence-transformers

echo.
echo [2/7] NoLlama health http://127.0.0.1:8000/health ...
call "%RUN_GPU%check_nollama_health.bat"
if errorlevel 1 goto :do_restart_nollama
echo [OK] NoLlama already responding
goto :after_nollama_restart

:do_restart_nollama
echo [WARN] NoLlama not responding. Starting...
call "%RUN_GPU%01_start_nollama.bat"
if errorlevel 1 (
    echo [FAIL] Could not start NoLlama. Run scripts\install_models\00_install_everything.bat
    set FAIL=1
    goto :summary
)

:after_nollama_restart

echo.
echo [3/7] Chat model %MODEL%...
python ensure_hermes_model.py --check
if errorlevel 1 (
    echo [WARN] Model not listed.
    set FAIL=1
    goto :summary
)
echo [OK] %MODEL% available

echo.
echo [4/7] Warmup %MODEL%...
call "%RUN_GPU%02_warmup_qwen14b.bat"
if errorlevel 1 (
    echo [FAIL] Chat warmup failed.
    set FAIL=1
    goto :summary
)
echo [OK] Chat path warm

echo.
echo [5/7] Local RAG embeddings (bge-m3)...
python -c "from hermes_embeddings import embed_texts; v=embed_texts(['probe'])[0]; print('[OK] dimensions', len(v))" 2>nul
if errorlevel 1 (
    echo [WARN] sentence-transformers embed failed.
)

echo.
echo [6/7] RAG index...
if exist "codebase_vectors.json" (
    echo [OK] codebase_vectors.json exists
) else (
    echo [WARN] No RAG index yet. Run: scripts\setup_index\01_build_index.bat
)

echo.
echo [7/7] Hermes preflight...
python hermes_preflight.py --quick --skip-cursor

:summary
echo.
echo ============================================================
if "%FAIL%"=="1" (
    echo   STARTUP FAILED - fix [FAIL] items above.
    echo ============================================================
    pause
    exit /b 1
)
echo   STARTUP OK - ready for Hermes
echo.
echo   python hermes_orchestrator.py "your task"
echo ============================================================
pause
exit /b 0
