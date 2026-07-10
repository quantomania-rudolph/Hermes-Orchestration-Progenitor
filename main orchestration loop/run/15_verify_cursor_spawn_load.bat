@echo off
setlocal
cd /d "%~dp0..\.."
echo === Cursor spawn preflight (quick) ===
python "daedalus\verification\load_strategies\verify_spawn_preflight.py"
exit /b %ERRORLEVEL%
