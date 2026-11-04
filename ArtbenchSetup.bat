@echo off
REM Connect a Unity project to Artbench in project mode (its art inventory, no art folder):
REM   ArtbenchSetup.bat "C:\path\to\YourUnityProject" [--name "Name"] [--mcp claude]
if "%~1"=="" (
  echo Usage: ArtbenchSetup.bat "path to your Unity project" [--name "Name"] [--mcp claude]
  pause
  exit /b 2
)
set "TARGET=%~f1"
cd /d "%~dp0"
REM Every argument after the folder goes on to the setup command, as typed.
set "REST="
:collect
shift
if "%~1"=="" goto run
set REST=%REST% %1
goto collect
:run
REM The portable folder brings its own Python; else the one installed on this machine.
if not exist "%~dp0python\python.exe" goto system
"%~dp0python\python.exe" -m artbench setup "%TARGET%"%REST%
goto finish
:system
where py >nul 2>nul
if %errorlevel%==0 (py -3 -m artbench setup "%TARGET%"%REST%) else (python -m artbench setup "%TARGET%"%REST%)
:finish
set "CODE=%errorlevel%"
pause
exit /b %CODE%
