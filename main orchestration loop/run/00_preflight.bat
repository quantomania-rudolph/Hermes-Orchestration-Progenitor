@echo off
setlocal
cd /d "%~dp0\..\.."
echo === HERMES Main Loop Preflight ===
python hermes_preflight.py --quick --skip-cursor
if errorlevel 1 exit /b 1
python "main orchestration loop\verification\verify_tool_registry.py"
if errorlevel 1 exit /b 1
python "main orchestration loop\verification\verify_index_bridge.py"
if errorlevel 1 exit /b 1
echo [OK] Preflight passed
exit /b 0
