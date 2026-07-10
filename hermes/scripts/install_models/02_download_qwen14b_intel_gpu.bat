@echo off
rem Step 2: NoLlama venv + Qwen3-14B-int4-ov download + Intel Arc GPU start.ps1.
cd /d "%~dp0"

if "%NOLLAMA_HOME%"=="" set "NOLLAMA_HOME=C:\Users\Rudol\NoLlama"
if not "%~1"=="" set "NOLLAMA_HOME=%~1"

if not exist "%NOLLAMA_HOME%\nollama.py" (
    echo [error] NoLlama not cloned. Run 01_clone_nollama_repo.bat first.
    pause
    exit /b 1
)

echo === [2/3] Download Qwen3-14B for Intel Arc GPU (~8 GB) ===
echo     NOLLAMA_HOME=%NOLLAMA_HOME%

echo [prep] Stopping stock Ollama on port 11434 if present...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":11434" ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>&1
taskkill /IM ollama.exe /F >nul 2>&1

pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_hermes_gpu.ps1" -NollamaHome "%NOLLAMA_HOME%"
if errorlevel 1 (
    echo [FAIL] install_hermes_gpu.ps1 failed
    pause
    exit /b 1
)

setx NOLLAMA_HOME "%NOLLAMA_HOME%" >nul
setx HERMES_CHAT_MODEL "qwen3-14b-int4" >nul
echo.
echo [OK] Qwen3-14B GPU model installed. Open a NEW CMD for setx vars.
exit /b 0
