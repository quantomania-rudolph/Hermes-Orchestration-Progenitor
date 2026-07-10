@echo off
rem Master install: runs all model download steps in order (requires internet).
cd /d "%~dp0"

echo === Hermes model install (steps 01-03) ===
echo.

call "%~dp001_clone_nollama_repo.bat"
if errorlevel 1 exit /b 1

call "%~dp002_download_qwen14b_intel_gpu.bat"
if errorlevel 1 exit /b 1

call "%~dp003_install_python_packages.bat"
if errorlevel 1 exit /b 1

echo.
echo === Running verification (step 04) ===
call "%~dp004_verify_all_models_installed.bat"
exit /b %ERRORLEVEL%
