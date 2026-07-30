@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_ducktales.ps1" %*
exit /b %errorlevel%
