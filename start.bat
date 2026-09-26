@echo off
rem FrameGuard - start service in background (Windows)
rem Usage: start.bat [--port 7891]

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" serve.py start %*
) else (
  python serve.py start %*
)
