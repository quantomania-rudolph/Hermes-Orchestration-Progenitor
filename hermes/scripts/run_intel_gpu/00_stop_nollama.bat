@echo off
rem Stop NoLlama listeners on ports 8000 (OpenAI API) and 11434 (Ollama-compat).
cd /d "%~dp0"

echo.
echo [stop] Freeing NoLlama ports 8000 and 11434...

for %%P in (8000 11434) do (
    for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":%%P" ^| findstr "LISTENING"') do (
        if not "%%i"=="0" (
            echo        port %%P - taskkill PID %%i
            taskkill /F /PID %%i >nul 2>&1
        )
    )
)

timeout /t 2 /nobreak >nul

set BLOCKED=0
for %%P in (8000 11434) do (
    netstat -ano | findstr ":%%P" | findstr "LISTENING" >nul 2>&1
    if not errorlevel 1 (
        echo [warn] Port %%P still in use.
        set BLOCKED=1
    )
)

if "%BLOCKED%"=="1" (
    echo Close the NoLlama window or end the Python process, then run this again.
    if not "%~1"=="nopause" pause
    exit /b 1
)

echo [ok] Ports 8000 and 11434 are free. Start with 01_start_nollama.bat
if not "%~1"=="nopause" pause
exit /b 0
