@echo off
echo Removing ControlHub startup shortcut...

del "ControlHub.exe" 2>null
del ".env" 2>null