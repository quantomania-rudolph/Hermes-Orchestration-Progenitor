@echo off
rem Full Intel GPU startup: start NoLlama, warmup Qwen14B, verify GPU access.
cd /d "%~dp0"

echo === Intel GPU startup (steps 01 → 02 → 04) ===
echo.

call "%~dp001_start_nollama.bat"
if errorlevel 1 exit /b 1

call "%~dp002_warmup_qwen14b.bat"
if errorlevel 1 exit /b 1

call "%~dp004_verify_gpu_access.bat"
exit /b %ERRORLEVEL%
