@echo off
:: Automatically switch to the directory containing this .bat file
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
title AI Server Pipeline is starting...
powershell -ExecutionPolicy Bypass -File .\run-server.ps1
pause
