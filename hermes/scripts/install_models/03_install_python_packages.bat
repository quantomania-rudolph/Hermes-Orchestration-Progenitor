@echo off
rem Step 3: Install Hermes Python dependencies (sentence-transformers, openai, etc.).
cd /d "%~dp0\..\.."

echo === [3/3] Install Hermes Python packages ===
python -m pip install -r requirements-hermes.txt
if errorlevel 1 (
    echo [FAIL] pip install failed
    pause
    exit /b 1
)

echo [OK] requirements-hermes.txt installed
exit /b 0
