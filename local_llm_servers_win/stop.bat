@echo off
cd /d "%~dp0"

:: Automatically request administrator privileges if needed
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :run
) else (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process -FilePath '%0' -Verb RunAs"
    exit /b
)

:run
title AI Server Pipeline is stopping...
powershell -ExecutionPolicy Bypass -File .\stop-server.ps1
pause
