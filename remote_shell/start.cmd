@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
set "KIRA_EXIT_CODE=%ERRORLEVEL%"
echo.
echo Launcher stopped. Exit code: %KIRA_EXIT_CODE%
pause
exit /b %KIRA_EXIT_CODE%
