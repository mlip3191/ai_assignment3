@echo off
rem AI Jukebox launcher for Windows (PROJECT.md section 0.4).
rem Double-click it, or type .\run.bat in a terminal in the app folder.
rem It finds Python 3.11+, makes the .venv folder, then hands off to scripts\launcher.py,
rem which does the rest the same way as run.sh on macOS. It calls .venv\Scripts\python.exe
rem directly, so nothing here depends on the downloaded-file script policy.
setlocal
set "CODE=0"
set "PY="

rem pushd also works for a network folder, where cd /d would fail and leave us in the wrong place.
pushd "%~dp0" 2>nul
if errorlevel 1 (
  echo Couldn't open the app folder. Copy it to your own drive, for example C:\jukebox, and run it from there.
  set "CODE=1"
  goto :fail
)

if not exist "scripts\launcher.py" (
  echo This launcher can't find the rest of the app.
  echo Extract the whole ZIP first: right-click it, choose Extract All, then run run.bat in the extracted folder.
  set "CODE=1"
  goto :fail
)

py -3.12 --version >nul 2>&1 && set "PY=py -3.12"
if not defined PY py -3.11 --version >nul 2>&1 && set "PY=py -3.11"
rem py -3 finds a newer Python, like 3.13 or 3.14, even when "Add python.exe to PATH" was skipped.
if not defined PY py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"

if not defined PY (
  echo Python 3.11 or newer was not found.
  echo Install Python 3.12 from python.org/downloads and tick "Add python.exe to PATH" on the first screen.
  echo Then close this window, open a new one, and run the launcher again.
  set "CODE=1"
  goto :fail
)

rem A .venv made by a Python that was later uninstalled can't run; rebuild it.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
  if errorlevel 1 (
    echo The .venv folder was made by a Python that is no longer installed. Rebuilding it...
    rmdir /s /q .venv
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Setting up the app's Python environment in the .venv folder, one time only...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Couldn't create the .venv folder. Make sure the app folder isn't inside OneDrive and that you can write to it, then try again.
    set "CODE=1"
    goto :fail
  )
)

".venv\Scripts\python.exe" scripts\launcher.py %*
set "CODE=%ERRORLEVEL%"
if "%CODE%"=="0" goto :done

:fail
echo.
pause

:done
endlocal & exit /b %CODE%
