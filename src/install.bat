@echo off
setlocal enabledelayedexpansion

python -c "import sys; print(sys.version_info >= (3,9))" 2>nul | findstr "True" >nul
if %errorlevel% neq 0 (
    echo Python 3.9+ not found. Installing Python 3.12.6...
    curl -o python-3.12.6-amd64.exe https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe
    echo Installing python, check opened admin window
    python-3.12.6-amd64.exe /quiet TargetDir="%USERPROFILE%\Python312" PrependPath=1 Include_pip=1
    del python_installer.exe
    echo Python 3.12.6 with pip installed successfully.
) else (
    echo Python 3.9+ is already installed.
)

:: Обновляем PATH вручную
set "PY_DIR=%USERPROFILE%\Python312"
setx PATH "%PATH%;%PY_DIR%;%PY_DIR%\Scripts" >nul
set "PATH=%PATH%;%PY_DIR%;%PY_DIR%\Scripts"

:: Устанавливаем Python-библиотеки
python -m pip install -r requirements.txt

:: Создаём ярлык для ControlHub.exe
echo Set oWS = WScript.CreateObject("WScript.Shell") > CreateShortcut.vbs
echo sLinkFile = "%~dp0ControlHub.lnk" >> CreateShortcut.vbs
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> CreateShortcut.vbs
echo oLink.TargetPath = "%~dp0ControlHub.exe" >> CreateShortcut.vbs
echo oLink.WorkingDirectory = "%~dp0" >> CreateShortcut.vbs
echo oLink.Save >> CreateShortcut.vbs
cscript CreateShortcut.vbs
del CreateShortcut.vbs

:: Перемещаем ярлык в автозагрузку
move "%~dp0ControlHub.lnk" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

start "" "%~dp0ControlHub.exe"