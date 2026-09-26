@echo off
rem FrameGuard - stop background service (Windows)
rem Usage: stop.bat [--port 7891]

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" serve.py stop %*
) else (
  python serve.py stop %*
)
