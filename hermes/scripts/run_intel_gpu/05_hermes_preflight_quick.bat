@echo off
cd /d "%~dp0\..\.."
python hermes_preflight.py --quick --skip-cursor
pause
