@echo off
setlocal
cd /d "%~dp0"

echo Starting AI Automation Console formal version...
echo.
echo This starts:
echo - frontend: http://127.0.0.1:3000
echo - backend:  http://127.0.0.1:8000
echo.

docker compose up --build -d
if errorlevel 1 (
  echo.
  echo Failed to start. Make sure Docker Desktop is running.
  pause
  exit /b 1
)

echo.
echo Started. Opening browser...
start "" "http://127.0.0.1:3000"
echo.
echo You can close this window. Use stop-formal.bat to stop the service.
pause
