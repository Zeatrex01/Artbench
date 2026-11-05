@echo off
REM Builds the downloads, each with its own Python (nothing to install). Double-click: a menu (Windows, macOS Apple
REM silicon, macOS Intel, or all). Or give tools\build_portable.py's options, e.g. Build.bat --target mac-x64.
REM Needs Python 3.11+ on this computer and, the first time, the internet (each Python is kept in dist\cache).
cd /d "%~dp0"
set "ARGS=%*"
if "%~1"=="" set "ARGS=--menu"
where py >nul 2>nul
if %errorlevel%==0 (py -3 tools\build_portable.py %ARGS%) else (python tools\build_portable.py %ARGS%)
if errorlevel 1 (
  echo.
  echo The build failed: the lines above say why.
  pause
  exit /b 1
)
echo.
echo Done: the zips are in the dist folder.
start "" "%~dp0dist"
pause
