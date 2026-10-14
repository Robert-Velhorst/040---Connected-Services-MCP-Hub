@echo off
setlocal
title Trello connector - Status check

set "APP=%~dp0trello"
set "PY=%APP%\.venv\Scripts\python.exe"
set "IMAGE=trello-mcp:latest"
set "VOLUME=trello-mcp-data"

echo.
echo  ==========================================================
echo   Trello connector  -  Status check
echo  ==========================================================
echo.

if exist "%PY%" goto :pythonmode

where docker >nul 2>&1
if errorlevel 1 goto :notinstalled
docker image inspect "%IMAGE%" >nul 2>&1
if errorlevel 1 goto :notinstalled
goto :dockermode

REM ---------------------------------------------------------------- Docker
:dockermode
echo  Install type: Docker
echo.
docker info >nul 2>&1
if errorlevel 1 (
    echo  [X] Docker Desktop is NOT running - the connector cannot start.
    echo      Start Docker Desktop and try again.
    echo.
    pause
    exit /b 1
)
echo  [ok] Docker Desktop is running
echo.

echo  -- Connection ------------------------------------------
docker run --rm --env-file "%APP%\.env" -v "%VOLUME%:/data" "%IMAGE%" python selftest.py
echo.
echo  -- How much of your account is indexed ------------------
docker run --rm --env-file "%APP%\.env" -v "%VOLUME%:/data" "%IMAGE%" python status.py
echo.
echo  -- Registration with the ChatGPT app --------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$c=Join-Path $env:USERPROFILE '.codex\config.toml'; if(Test-Path $c){ $t=Get-Content $c -Raw; if($t -match '(?ms)^\[mcp_servers\.trello\].*?(?=^\[(?!mcp_servers\.trello\.)|\Z)'){ Write-Output $Matches[0].Trim() } else { Write-Output 'NOT REGISTERED' } } else { Write-Output 'config.toml not found' }"
goto :end

REM ---------------------------------------------------------------- Python
:pythonmode
echo  Install type: local Python
echo.
echo  -- Connection ------------------------------------------
"%PY%" "%APP%\selftest.py"
echo.
echo  -- Registration with the ChatGPT app --------------------
"%PY%" "%APP%\setup_codex.py" --check
echo.
echo  -- How much of your account is indexed ------------------
"%PY%" "%APP%\status.py"

:end
echo.
echo  ==========================================================
echo   Send this whole window to your developer if anything
echo   above looks wrong.
echo  ==========================================================
echo.
pause
exit /b 0

:notinstalled
echo  [X] Not installed yet.
echo      Run install.bat  (if you have Python)
echo      or install-docker.bat  (if you use Docker).
echo.
pause
exit /b 1
