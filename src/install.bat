@echo off
setlocal enabledelayedexpansion

:: Initializing ControlHub logs
if not exist "%PROGRAMDATA%\ControlHub\logs" (
    mkdir "%PROGRAMDATA%\ControlHub\logs"
)
type nul > "%PROGRAMDATA%\ControlHub\logs\process.log"
type nul > "%PROGRAMDATA%\ControlHub\logs\error.log"

icacls "%PROGRAMDATA%\ControlHub" /grant *S-1-5-32-545:(OI)(CI)M /T

:: Download and install pip requirements
python\python.exe -m pip install --upgrade -r requirements.txt

start "" "%~dp0ControlHub.exe"