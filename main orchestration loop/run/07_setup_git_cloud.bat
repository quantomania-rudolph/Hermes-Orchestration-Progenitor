@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0\..\.."
echo === HERMES Git Setup for Cloud Agents ===
echo.

if not exist ".git" (
  echo Initializing git repository...
  git init -b main
  git config user.email "hermes@local"
  git config user.name "HERMES Local"
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo.
  echo No GitHub remote yet. Create a repo at https://github.com/new then run:
  echo   git remote add origin https://github.com/YOUR_USER/Hermes_Orchestration.git
  echo   git push -u origin main
  echo.
  set /p REMOTE_URL="Paste origin URL (or press Enter to skip): "
  if not "!REMOTE_URL!"=="" (
    git remote add origin "!REMOTE_URL!"
  )
) else (
  echo [OK] origin: 
  git remote get-url origin
)

echo.
echo Staging and committing project files...
git add -A
git status --short
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "hermes: initial commit for cloud agents"
) else (
  echo [OK] Nothing new to commit
)

git remote get-url origin >nul 2>&1
if not errorlevel 1 (
  echo.
  echo Pushing to origin/main...
  git push -u origin main
  if errorlevel 1 (
    echo [WARN] Push failed — authenticate with GitHub then re-run this script
    exit /b 1
  )
  echo [OK] Cloud agents can clone this repo
) else (
  echo [WARN] Add origin remote and push before running 06_run_cloud_trading_test.bat
)

exit /b 0
