@echo off
setlocal enabledelayedexpansion

python -c "import sys; print(sys.version_info >= (3,9))" 2>nul | findstr "True" >nul
if %errorlevel% neq 0 (
    echo Python 3.9+ not found. Installing Python 3.12.6...
    curl -o python_installer.exe https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe
    echo Installing python, check opened admin window
    python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_test=0
    del python_installer.exe
    echo Python 3.12.6 with pip installed successfully.
) else (
    echo Python 3.9+ is already installed.
)

:: Устанавливаем Python-библиотеки
python -m pip install -r requirements.txt

:: Создаём ярлык для run.bat
echo Set oWS = WScript.CreateObject("WScript.Shell") > CreateShortcut.vbs
echo sLinkFile = "%~dp0ControlHub.lnk" >> CreateShortcut.vbs
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> CreateShortcut.vbs
echo oLink.TargetPath = "%~dp0run.bat" >> CreateShortcut.vbs
echo oLink.WorkingDirectory = "%~dp0" >> CreateShortcut.vbs
echo oLink.Save >> CreateShortcut.vbs
cscript CreateShortcut.vbs
del CreateShortcut.vbs

:: Перемещаем ярлык в автозагрузку
move "%~dp0ControlHub.lnk" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
./run.bat
