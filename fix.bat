@echo off
setlocal EnableDelayedExpansion
title Trello connector - Fix it

set "ROOT=%~dp0"
set "APP=%ROOT%trello"

echo.
echo  ==========================================================
echo   Trello connector  -  automatic setup, diagnose and repair
echo  ==========================================================
echo.

REM A fresh unzip has no credentials file, because the zip deliberately ships
REM without one. In that case this is a FIRST INSTALL, not a repair, so hand
REM straight over to the installer instead of stopping with a confusing
REM "credentials missing" message. One button then covers both cases.
if not exist "%APP%\.env" (
    echo   No credentials found - this looks like a first install.
    echo.
    REM Choose by what this machine actually has, not by what the folder
    REM contains: a fresh unzip has neither .venv nor .env.
    set "USEDOCKER="
    where docker >nul 2>&1 && (
        docker info >nul 2>&1 && set "USEDOCKER=1"
    )
    if defined USEDOCKER (
        echo   Docker is available - running the Docker installer.
        echo.
        call "%ROOT%install-docker.bat" %*
    ) else (
        echo   Running the standard installer.
        echo.
        call "%ROOT%install.bat" %*
    )
    exit /b %ERRORLEVEL%
)

REM Runs on ANY Python (standard library only), and if there is no Python at
REM all it falls back to running inside the container.
set "PYEXE="
set "PYARG="
if exist "%APP%\.venv\Scripts\python.exe" (
    set "PYEXE=%APP%\.venv\Scripts\python.exe"
) else (
    for %%V in (3.13 3.12 3) do (
        if not defined PYEXE (
            py -%%V -c "import sys" >nul 2>&1 && (
                set "PYEXE=py"
                set "PYARG=-%%V"
            )
        )
    )
    if not defined PYEXE (
        python -c "import sys" >nul 2>&1 && set "PYEXE=python"
    )
)

if defined PYEXE (
    "%PYEXE%" %PYARG% "%APP%\repair.py" %*
    set "RC=!ERRORLEVEL!"
    goto :done
)

REM ---- No Python on this PC: do the Docker-only checks here in batch ----
echo   No Python on this computer - running Docker checks directly.
echo.

where docker >nul 2>&1
if errorlevel 1 (
    echo   [STOP] Docker is not installed.
    echo          Install Docker Desktop, then run install-docker.bat
    echo          https://www.docker.com/products/docker-desktop/
    set "RC=1"
    goto :done
)
echo   [ok]   Docker is installed

docker info >nul 2>&1
if errorlevel 1 (
    echo   [STOP] Docker Desktop is NOT RUNNING.
    echo          Start Docker Desktop, wait for "Engine running", run this again.
    set "RC=1"
    goto :done
)
echo   [ok]   Docker Desktop is running

docker image inspect trello-mcp:latest >nul 2>&1
if errorlevel 1 (
    echo   [....] Container image missing - rebuilding, please wait 2-4 minutes...
    docker build -t trello-mcp:latest "%APP%"
    if errorlevel 1 (
        echo   [STOP] The image failed to build. Send the output above to your developer.
        set "RC=1"
        goto :done
    )
    echo   [FIXED] Container image rebuilt
) else (
    echo   [ok]   Container image present
)

docker volume inspect trello-mcp-data >nul 2>&1
if errorlevel 1 docker volume create trello-mcp-data >nul 2>&1
echo   [ok]   Storage volume ready

if not exist "%APP%\.env" (
    echo   [STOP] Credentials missing. Run install-docker.bat first.
    set "RC=1"
    goto :done
)
echo   [ok]   Credentials file present

REM Now that the image exists, run the full repair INSIDE the container so the
REM remaining checks still happen on a Python-free machine.
docker run --rm --env-file "%APP%\.env" -v "trello-mcp-data:/data" ^
    trello-mcp:latest python repair.py --dry-run
set "RC=!ERRORLEVEL!"

echo.
echo   Re-registering with the ChatGPT app...
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP%\register-docker.ps1" ^
    -EnvFile "%APP%\.env" -Image "trello-mcp:latest" -Volume "trello-mcp-data"

:done
echo.
echo  ==========================================================
echo   IMPORTANT - do this now:
echo     1. Fully QUIT the ChatGPT app (right-click the taskbar
echo        icon near the clock, choose Quit). Closing the
echo        window is NOT enough.
echo     2. Open ChatGPT again.
echo     3. Ask it:  "Use trello_account_overview and tell me
echo        how many workspaces and boards I have."
echo  ==========================================================
echo.
pause
exit /b %RC%
