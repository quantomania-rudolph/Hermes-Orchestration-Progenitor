@echo off
rem Incremental codebase index -> codebase_vectors.json in project root.
cd /d "%~dp0\..\.."
if "%HERMES_WORKSPACE_ROOTS%"=="" set "HERMES_WORKSPACE_ROOTS=%~dp0..\.."
echo === Build RAG index (incremental) ===
echo     Roots: %HERMES_WORKSPACE_ROOTS%
python -u scripts\setup_index\build_index.py %*
set EXIT=%ERRORLEVEL%
if not "%EXIT%"=="0" pause
exit /b %EXIT%
