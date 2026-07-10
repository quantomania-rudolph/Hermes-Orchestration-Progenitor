@echo off
rem Prove incremental index: reuse unchanged files, embed new ones, drop deleted ones.
cd /d "%~dp0\..\.."
if "%HERMES_WORKSPACE_ROOTS%"=="" set "HERMES_WORKSPACE_ROOTS=%~dp0..\.."

echo === Incremental index growth test ===
echo.

echo [1/4] Baseline incremental run (should mostly reuse if index exists)...
python -u scripts\setup_index\build_index.py
if errorlevel 1 exit /b 1

echo.
echo [2/4] Adding probe file...
echo PROBE_VERSION = 1> scripts\setup_index\_incremental_growth_probe.py

echo [3/4] Incremental run after add (expect embedded^>=1, reused^>=1)...
python -u scripts\setup_index\build_index.py
if errorlevel 1 exit /b 1

echo.
echo [4/4] Removing probe file and syncing index...
del /f scripts\setup_index\_incremental_growth_probe.py
python -u scripts\setup_index\build_index.py
if errorlevel 1 exit /b 1

python scripts\setup_index\verify_index.py
exit /b %ERRORLEVEL%
