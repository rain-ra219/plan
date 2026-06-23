@echo off
setlocal
cd /d "%~dp0"

echo Rebuilding backend only...
echo This applies backend code changes without rebuilding the frontend image.
echo.

docker compose up --build --pull never -d backend
set EXIT_CODE=%ERRORLEVEL%

echo.
if "%EXIT_CODE%"=="0" (
  echo Backend refresh finished.
) else (
  echo Backend refresh failed. Send this window screenshot to Codex.
)
pause
exit /b %EXIT_CODE%
