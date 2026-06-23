@echo off
setlocal
cd /d "%~dp0"

echo Testing platform main-image workflow...
echo Backend API: http://127.0.0.1:8000
echo.

python scripts\test_platform_main_image.py --api http://127.0.0.1:8000
set EXIT_CODE=%ERRORLEVEL%

echo.
if "%EXIT_CODE%"=="0" (
  echo SUCCESS: real image generation workflow returned API result.
) else (
  echo FAILED: copy the error above or send a screenshot to Codex.
)
pause
exit /b %EXIT_CODE%
