@echo off
rem EA Explorer launcher for Windows: runs eax.ps1 with the execution policy bypassed for this run only
rem (the script is not signed). Usage: eax <command> [options]   e.g.  eax up   or   eax help
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0eax.ps1" %*
exit /b %ERRORLEVEL%
