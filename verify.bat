@echo off
setlocal
title Trello connector - Acceptance test

set "APP=%~dp0trello"
set "PY=%APP%\.venv\Scripts\python.exe"
set "IMAGE=trello-mcp:latest"
set "VOLUME=trello-mcp-data"

REM Works with either install: local Python, or Docker on a Python-free PC.
if exist "%PY%" (
    "%PY%" "%APP%\verify.py"
    set "RC=%ERRORLEVEL%"
    goto :done
)

where docker >nul 2>&1
if errorlevel 1 goto :notinstalled
docker image inspect "%IMAGE%" >nul 2>&1
if errorlevel 1 goto :notinstalled

docker info >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [X] Docker Desktop is not running. Start it, wait for
    echo      "Engine running", then try again.
    echo.
    pause
    exit /b 1
)

docker run --rm --env-file "%APP%\.env" -v "%VOLUME%:/data" "%IMAGE%" python verify.py
set "RC=%ERRORLEVEL%"

:done
echo.
if "%RC%"=="0" (
    echo  Everything is working. You can close this window.
) else (
    echo  Something failed above - please send this window to your developer.
)
echo.
pause
exit /b %RC%

:notinstalled
echo.
echo  [X] Not installed yet.
echo      Run install.bat  (if you have Python)
echo      or install-docker.bat  (if you use Docker).
echo.
pause
exit /b 1
