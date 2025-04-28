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
python\python.exe -m pip install --upgrade --no-cache-dir -r requirements.txt

:: Creating ControlHub shortcut in startup folder
echo Set oWS = WScript.CreateObject("WScript.Shell") > CreateShortcut.vbs
echo sLinkFile = "%~dp0ControlHub.lnk" >> CreateShortcut.vbs
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> CreateShortcut.vbs
echo oLink.TargetPath = "%~dp0ControlHub.exe" >> CreateShortcut.vbs
echo oLink.WorkingDirectory = "%~dp0" >> CreateShortcut.vbs
echo oLink.Save >> CreateShortcut.vbs
cscript CreateShortcut.vbs
del CreateShortcut.vbs

:: Moving the shortcut to the startup folder
move "%~dp0ControlHub.lnk" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

start "" "%~dp0ControlHub.exe"