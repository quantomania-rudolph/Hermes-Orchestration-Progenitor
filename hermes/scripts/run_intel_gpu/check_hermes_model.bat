@echo off
rem Check NoLlama health and that HERMES_CHAT_MODEL is listed.
cd /d "%~dp0\..\.."
python ensure_hermes_model.py --check
if errorlevel 1 (
    echo [FAIL] See errors above.
    pause
    exit /b 1
)
echo.
echo [OK] NoLlama chat model ready.
exit /b 0
