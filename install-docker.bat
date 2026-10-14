@echo off
setlocal EnableDelayedExpansion
title Trello connector for ChatGPT - Docker setup

set "ROOT=%~dp0"
set "APP=%ROOT%trello"
set "ENVFILE=%APP%\.env"
set "IMAGE=trello-mcp:latest"
set "VOLUME=trello-mcp-data"

echo.
echo  ==========================================================
echo   Trello connector for ChatGPT  -  Docker setup
echo   (no Python needed on this computer)
echo  ==========================================================
echo.

REM ------------------------------------------------------------ check docker
where docker >nul 2>&1
if errorlevel 1 (
    echo  [X] Docker was not found on this computer.
    echo.
    echo      Install Docker Desktop from:
    echo         https://www.docker.com/products/docker-desktop/
    echo      Then start it and run this again.
    echo.
    pause
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo  [X] Docker is installed but not running.
    echo.
    echo      Start Docker Desktop, wait until it says "Engine running",
    echo      then run this again.
    echo.
    pause
    exit /b 1
)
echo  [1/5] Docker is installed and running.

REM ------------------------------------------------------------ credentials
if exist "%ENVFILE%" (
    echo  [2/5] Existing credentials found - keeping them.
    goto :haveenv
)

set "TKEY=%~1"
set "TTOK=%~2"

if not "%TKEY%"=="" if not "%TTOK%"=="" (
    echo  [2/5] Using credentials passed on the command line.
    goto :writeenv
)

echo  [2/5] Trello credentials needed.
echo.
echo        Get them at: https://trello.com/power-ups/admin
echo.
set /p "TKEY=        Trello API key   : "
set /p "TTOK=        Trello API token : "

:writeenv
if "%TKEY%"=="" goto :nocreds
if "%TTOK%"=="" goto :nocreds
REM Written without quotes or spaces: docker --env-file is strict about format.
>"%ENVFILE%" echo TRELLO_API_KEY=%TKEY%
>>"%ENVFILE%" echo TRELLO_TOKEN=%TTOK%
>>"%ENVFILE%" echo TRELLO_READ_ONLY=true
>>"%ENVFILE%" echo TRELLO_CACHE_ENABLED=true
>>"%ENVFILE%" echo TRELLO_SYNC_ON_START=true
>>"%ENVFILE%" echo TRELLO_SYNC_INTERVAL_SECONDS=900
echo.
echo        Saved to trello\.env

:haveenv

REM ------------------------------------------------------------ build image
echo  [3/5] Building the container image (first time takes 2-4 minutes)...
docker build -q -t "%IMAGE%" "%APP%" >nul
if errorlevel 1 (
    echo.
    echo  [X] The image failed to build. Showing the full output:
    echo.
    docker build -t "%IMAGE%" "%APP%"
    goto :failed
)
echo        Image built: %IMAGE%

docker volume create "%VOLUME%" >nul 2>&1
echo        Storage volume ready: %VOLUME%

REM ------------------------------------------------------------ self test
echo  [4/5] Checking the connector can reach Trello...
docker run --rm --env-file "%ENVFILE%" -v "%VOLUME%:/data" "%IMAGE%" python selftest.py
if errorlevel 1 goto :failed

REM ------------------------------------------------------------ register
REM Done with PowerShell (built into Windows) rather than Python, so the host
REM stays Python-free. -ExecutionPolicy Bypass applies to this call only and
REM does not change any machine setting.
echo  [5/5] Registering with the ChatGPT app...
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP%\register-docker.ps1" ^
    -EnvFile "%ENVFILE%" -Image "%IMAGE%" -Volume "%VOLUME%"
if errorlevel 1 goto :failed

echo.
echo  ==========================================================
echo   Setup complete.
echo  ==========================================================
echo.
echo   NEXT STEP - this part matters:
echo.
echo     1. Fully QUIT the ChatGPT app.
echo        Right-click its taskbar icon and choose Quit -
echo        closing the window is not enough.
echo     2. Open ChatGPT again.
echo     3. Settings  -^>  Plugins  -^>  MCPs  -^>  you should see "trello".
echo.
echo   IMPORTANT: Docker Desktop must be running whenever you
echo   use the Trello connector in ChatGPT.
echo.
echo   Then ask ChatGPT:  "Give me an overview of my Trello account."
echo   The first answer takes about 90 seconds while it indexes.
echo.
pause
exit /b 0

:nocreds
echo.
echo  [X] Both the API key and token are required. Nothing was changed.
echo.
pause
exit /b 1

:failed
echo.
echo  [X] Setup did not complete. Please send the messages above to your developer.
echo.
pause
exit /b 1
