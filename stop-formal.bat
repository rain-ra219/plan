@echo off
setlocal
cd /d "%~dp0"

echo Stopping AI Automation Console formal version...
docker compose stop
if errorlevel 1 (
  echo.
  echo Failed to stop. Make sure Docker Desktop is running.
  pause
  exit /b 1
)

echo.
echo Stopped.
pause
