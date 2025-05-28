@echo off
set PYTHONNOUSERSITE=1
set PYTHONUSERBASE=
set PIP_USER=false
set PIP_PREFIX=
set PIP_TARGET=%~dp0Lib\site-packages

"%~dp0python.exe" %*