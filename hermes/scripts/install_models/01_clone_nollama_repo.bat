@echo off
rem Step 1: Clone the NoLlama OpenVINO backend repo.
cd /d "%~dp0"

if "%NOLLAMA_HOME%"=="" set "NOLLAMA_HOME=C:\Users\Rudol\NoLlama"
if not "%~1"=="" set "NOLLAMA_HOME=%~1"

echo === [1/3] Clone NoLlama repo ===
echo     NOLLAMA_HOME=%NOLLAMA_HOME%

if exist "%NOLLAMA_HOME%\nollama.py" (
    echo [OK] Already cloned: %NOLLAMA_HOME%
    exit /b 0
)

git clone https://github.com/aweussom/NoLlama "%NOLLAMA_HOME%"
if errorlevel 1 (
    echo [FAIL] git clone failed
    pause
    exit /b 1
)

echo [OK] Cloned to %NOLLAMA_HOME%
exit /b 0
