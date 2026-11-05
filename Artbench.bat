@echo off
REM Artbench from its source code: needs Python 3.11 or newer on this computer. Without it, the ready Windows build
REM is the easy way: it brings its own Python. https://github.com/Zeatrex01/Artbench/releases/latest
cd /d "%~dp0"
title Artbench
set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=py -3"
if defined PY goto run
where python >nul 2>nul && python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
if defined PY goto run
goto nopython
:run
%PY% -m artbench --app
if errorlevel 1 pause
exit /b
:nopython
echo.
echo   This folder is Artbench's source code, and it needs Python 3.11 or newer.
echo   This computer does not have it.
echo.
echo   The ready Windows build brings its own Python: nothing to install.
echo   It is downloading now. Unzip it anywhere and double-click Artbench.bat.
echo.
echo   https://github.com/Zeatrex01/Artbench/releases/latest/download/Artbench-windows-x64.zip
start "" "https://github.com/Zeatrex01/Artbench/releases/latest/download/Artbench-windows-x64.zip"
pause
