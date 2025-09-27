@echo off
REM scripts\launch_ibeam.bat
REM Usage: Double-click this file (or run from Explorer) to start the voyz/ibeam docker container.

SETLOCAL
REM Set the folder where env.list lives and where the command should run
SET TARGET_DIR=C:\Users\kevin\Desktop\trading\cpapi

REM Change to target directory (works across drives)
PUSHD "%TARGET_DIR%"
echo Working directory: %CD%

REM Quick docker presence check
docker --version >nul 2>&1
IF ERRORLEVEL 1 (
  echo.
  echo Docker not found in PATH. Please install Docker Desktop or ensure 'docker' is on your PATH.
  echo Press any key to close...
  pause >nul
  POPD
  EXIT /B 1
)

echo Starting voyz/ibeam (port 5000) from %CD%...

REM Open a new cmd window and run the docker command there so logs are visible.
start "ibeam" cmd /k "cd /d "%CD%" && docker run --env-file env.list -p 5000:5000 voyz/ibeam"

REM Return to original folder
POPD
ENDLOCAL
EXIT /B 0
