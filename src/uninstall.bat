@echo off
echo Removing ControlHub startup shortcut...
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ControlHub.lnk" 2>nul
echo ControlHub has been uninstalled successfully.
