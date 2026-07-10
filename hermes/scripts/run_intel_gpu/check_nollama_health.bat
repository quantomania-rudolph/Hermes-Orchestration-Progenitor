@echo off
rem Exit 0 if NoLlama health endpoint responds on :8000; exit 1 otherwise.
curl -sf --max-time 5 http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0
