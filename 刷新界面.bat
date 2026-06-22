@echo off
chcp 65001 >nul

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator permission...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

cd /d F:\plan

echo Refreshing AI Automation Console Lite...
echo.
docker compose up --build --pull never -d

if errorlevel 1 (
  echo.
  echo First build failed. Retrying with legacy Docker builder and local image cache...
  echo.
  set DOCKER_BUILDKIT=0
  set COMPOSE_DOCKER_CLI_BUILD=0
  docker compose up --build --pull never -d
)

echo.
if errorlevel 1 (
  echo Refresh failed. Please make sure Docker Desktop is running and your Windows user can access Docker.
) else (
  echo Refresh completed.
  echo Frontend: http://127.0.0.1:3000
  echo Backend:  http://127.0.0.1:8000
)
echo.
pause
