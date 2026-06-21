@echo off
setlocal
cd /d "%~dp0"

echo Starting AI Automation Console demo version...
echo.
echo This starts the single-container demo at:
echo http://127.0.0.1:8000
echo.

docker compose -f compose.demo.yaml up --build -d
if errorlevel 1 (
  echo.
  echo Failed to start. Make sure Docker Desktop is running.
  pause
  exit /b 1
)

echo.
echo Started. Opening browser...
start "" "http://127.0.0.1:8000"
echo.
echo You can close this window. Use stop-demo.bat to stop the service.
pause
