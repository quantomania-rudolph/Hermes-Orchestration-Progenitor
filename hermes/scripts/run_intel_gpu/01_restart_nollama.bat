@echo off
rem Stop NoLlama, then start a fresh Intel GPU instance.
cd /d "%~dp0"

call 00_stop_nollama.bat nopause
if errorlevel 1 exit /b 1
timeout /t 2 /nobreak >nul
call 01_start_nollama.bat
exit /b %ERRORLEVEL%
