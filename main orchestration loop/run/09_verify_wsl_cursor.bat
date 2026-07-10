@echo off
setlocal
cd /d "%~dp0\..\.."
echo === WSL Cursor CLI + SDK Verify ===
wsl -d Ubuntu-24.04 -u root -- bash "main orchestration loop/run/_wsl_verify_cursor.sh"
exit /b %ERRORLEVEL%
