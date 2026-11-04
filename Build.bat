@echo off
REM Builds the Windows download: dist\Artbench-<version>-windows-x64.zip, with its own Python (nothing to install).
REM Needs Python 3.11+ on this computer and, the first time, the internet (python.org's embeddable Python, kept in dist\cache).
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 tools\build_portable.py %*) else (python tools\build_portable.py %*)
if errorlevel 1 (
  echo.
  echo The build failed: the lines above say why.
  pause
  exit /b 1
)
echo.
echo Done: the zip is in the dist folder.
start "" "%~dp0dist"
pause
