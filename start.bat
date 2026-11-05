@echo off
title Synthesis Route Review - Local Server
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
echo.
echo The server window can now be closed. Any startup error is shown above.
pause
