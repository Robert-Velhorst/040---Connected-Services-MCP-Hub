@echo off
setlocal EnableDelayedExpansion
title Trello connector - Readiness check

set "APP=%~dp0trello"

echo.
echo  ==========================================================
echo   Trello connector  -  Readiness check
echo   (checks this computer, changes nothing)
echo  ==========================================================
echo.

REM Find any Python at all - preflight only needs the standard library.
REM Executable and version flag are kept apart: "py -3.12" is two tokens, and
REM quoting them as one path makes Windows look for a file called "py -3.12".
set "PYEXE="
set "PYARG="
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

if not defined PYEXE (
    echo   [STOP] No Python is installed on this computer.
    echo.
    where winget >nul 2>&1
    if errorlevel 1 (
        echo          winget is not available either, so Python must be
        echo          installed by hand from:
        echo             https://www.python.org/downloads/release/python-3130/
        echo          Tick "Add python.exe to PATH" on the first screen.
    ) else (
        echo          Good news: winget is available, so install.bat can
        echo          install Python automatically. Just run install.bat.
    )
    echo.
    pause
    exit /b 1
)

"%PYEXE%" %PYARG% "%APP%\preflight.py"
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" (
    echo   Next step: run install.bat
) else (
    echo   Resolve the items marked [STOP] above, then run this again.
)
echo.
pause
exit /b %RC%
