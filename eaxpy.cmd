@echo off
rem EA Explorer launcher (Python version, phase 13.9, D331): runs eaxpy.ps1, which fetches uv the first time and runs
rem eaxpy.py with it. Usage: eaxpy <command> [options]   e.g.  eaxpy up   or   eaxpy help
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0eaxpy.ps1" %*
exit /b %ERRORLEVEL%
