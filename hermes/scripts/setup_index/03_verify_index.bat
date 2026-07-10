@echo off
rem Verify codebase_vectors.json exists and contains embedded chunks.
cd /d "%~dp0\..\.."
python -u scripts\setup_index\verify_index.py %*
set EXIT=%ERRORLEVEL%
if not "%EXIT%"=="0" pause
exit /b %EXIT%
