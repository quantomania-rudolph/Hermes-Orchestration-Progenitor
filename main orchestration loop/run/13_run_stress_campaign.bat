@echo off
setlocal
cd /d "%~dp0\..\.."
echo === HERMES Stress Campaign (5 live runs, WSL) ===
echo Log: main orchestration loop\state\stress_campaign.log
wsl -d Ubuntu-24.04 -u root -- bash "main orchestration loop/run/13_run_stress_campaign.sh"
exit /b %ERRORLEVEL%
