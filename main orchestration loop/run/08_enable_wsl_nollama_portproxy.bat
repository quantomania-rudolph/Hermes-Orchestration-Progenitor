@echo off
:: Expose Windows NoLlama (:8000) to WSL2. Requires Administrator.
setlocal
net session >nul 2>&1
if errorlevel 1 (
  echo [FAIL] Run this script as Administrator
  exit /b 1
)
echo Adding portproxy 0.0.0.0:8000 -^> 127.0.0.1:8000 ...
netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=8000 >nul 2>&1
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8000 connectaddress=127.0.0.1 connectport=8000
netsh advfirewall firewall delete rule name="HERMES NoLlama WSL" >nul 2>&1
netsh advfirewall firewall add rule name="HERMES NoLlama WSL" dir=in action=allow protocol=TCP localport=8000 profile=private
echo [OK] WSL can reach NoLlama via default gateway :8000
echo Test from WSL: curl http://$(ip route ^| awk '/default/{print $3}'):8000/health
exit /b 0
