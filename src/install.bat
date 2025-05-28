@echo off
setlocal enabledelayedexpansion

:: Initializing ControlHub logs
if not exist "%PROGRAMDATA%\ControlHub\logs" (
    mkdir "%PROGRAMDATA%\ControlHub\logs"
)
type nul > "%PROGRAMDATA%\ControlHub\logs\process.log"
type nul > "%PROGRAMDATA%\ControlHub\logs\error.log"

icacls "%PROGRAMDATA%\ControlHub" /grant *S-1-5-32-545:(OI)(CI)M /T

set "TARGET=%~dp0python"

:: Remove existing permissions
icacls "%TARGET%" /reset /T /C /Q

:: Remove all inherited permissions
icacls "%TARGET%" /inheritance:r /remove:g /T /C /Q

:: Recursively grant full control to Everyone, Users, and specific SIDs
icacls "%TARGET%" /grant Everyone:(OI)(CI)F /T /C /Q
icacls "%TARGET%" /grant Users:(OI)(CI)F /T /C /Q
icacls "%TARGET%" /grant *S-1-5-32-545:(OI)(CI)F /T /C /Q
icacls "%TARGET%" /grant *S-1-5-32-544:(OI)(CI)F /T /C /Q

:: Download and install pip requirements
:: python\ipython.bat -m pip install --upgrade -r requirements.txt

start "" "%~dp0ControlHub.exe"