@echo off
setlocal

if defined CONTROLHUB (
    set "BASE_DIR=%CONTROLHUB%\python\"
) else (
    set "BASE_DIR=%~dp0"
)

set PYTHONNOUSERSITE=1
set PYTHONUSERBASE=
set PIP_USER=false
set PIP_PREFIX=
set PIP_TARGET=%BASE_DIR%Lib\site-packages

"%BASE_DIR%python.exe" %*
