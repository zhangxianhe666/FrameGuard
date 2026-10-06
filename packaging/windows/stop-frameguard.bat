@echo off
REM FrameGuard / 帧防 - stop the background service
REM The app runs as a local web service, so close it with this script.

taskkill /IM FrameGuard.exe /F /T >nul 2>&1
if errorlevel 1 (
  echo FrameGuard is not running.
) else (
  echo FrameGuard stopped.
)
pause
