@echo off
rem Full rebuild: re-embed every file in workspace roots.
cd /d "%~dp0\..\.."
if "%HERMES_WORKSPACE_ROOTS%"=="" set "HERMES_WORKSPACE_ROOTS=%~dp0..\.."
echo === Build RAG index (full rebuild) ===
echo     Roots: %HERMES_WORKSPACE_ROOTS%
python -u scripts\setup_index\build_index.py --full %*
set EXIT=%ERRORLEVEL%
if not "%EXIT%"=="0" pause
exit /b %EXIT%
