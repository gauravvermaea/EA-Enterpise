@echo off
rem EA Explorer installer for Windows (phase 36, D502): runs eax-deploy.ps1 beside it. See eax-deploy.ps1 for its options.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0eax-deploy.ps1" %*
exit /b %ERRORLEVEL%
