@echo off
setlocal
cd /d "%~dp0"

echo Stopping AI Automation Console demo version...
docker compose -f compose.demo.yaml stop
if errorlevel 1 (
  echo.
  echo Failed to stop. Make sure Docker Desktop is running.
  pause
  exit /b 1
)

echo.
echo Stopped.
pause
