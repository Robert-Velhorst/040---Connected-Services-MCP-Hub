@echo off
setlocal EnableDelayedExpansion
title Trello connector for ChatGPT - Setup

set "ROOT=%~dp0"
set "APP=%ROOT%trello"
set "VENV=%APP%\.venv"
set "PY=%VENV%\Scripts\python.exe"

echo.
echo  ==========================================================
echo   Trello connector for ChatGPT  -  Setup
echo  ==========================================================
echo.

REM ---------------------------------------------------------------- find python
REM The lockfile's pinned pydantic-core does not build on 3.14, so prefer 3.13/3.12.
REM Executable and version flag are kept apart: "py -3.12" is two tokens, and
REM quoting them as one path makes Windows look for a file called "py -3.12".
set "PYEXE="
set "PYARG="
for %%V in (3.13 3.12) do (
    if not defined PYEXE (
        py -%%V -c "import sys" >nul 2>&1 && (
            set "PYEXE=py"
            set "PYARG=-%%V"
        )
    )
)
if not defined PYEXE (
    python -c "import sys; assert (3,12) <= sys.version_info < (3,14)" >nul 2>&1 && set "PYEXE=python"
)

if not defined PYEXE (
    echo  [1/5] Python 3.12/3.13 not found - attempting automatic install...
    where winget >nul 2>&1
    if errorlevel 1 goto :nopython

    echo        Installing Python 3.13 via winget. This takes a few minutes.
    echo.
    winget install --id Python.Python.3.13 -e --source winget ^
        --accept-package-agreements --accept-source-agreements
    echo.

    REM winget updates PATH for NEW processes only, so re-probe via the
    REM launcher and the default per-user install location.
    for %%V in (3.13 3.12) do (
        if not defined PYEXE (
            py -%%V -c "import sys" >nul 2>&1 && (
                set "PYEXE=py"
                set "PYARG=-%%V"
            )
        )
    )
    if not defined PYEXE (
        if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
            set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
        )
    )
    if not defined PYEXE (
        echo  [!] Python was installed, but this window cannot see it yet.
        echo      Close this window and run install.bat again - it will work.
        echo.
        pause
        exit /b 1
    )
)
echo  [1/5] Python found: %PYEXE% %PYARG%

REM ---------------------------------------------------------------- credentials
REM Kept flat on purpose: a :label inside a parenthesised block is fragile in
REM cmd.exe, and this is the step a live setup session cannot afford to break.
set "ENVFILE=%APP%\.env"

if exist "%ENVFILE%" (
    echo  [2/5] Existing credentials found - keeping them.
    goto :haveenv
)

REM Credentials may be passed as arguments for unattended setup:
REM    install.bat <api-key> <api-token>
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
>"%ENVFILE%" echo TRELLO_API_KEY=%TKEY%
>>"%ENVFILE%" echo TRELLO_TOKEN=%TTOK%
>>"%ENVFILE%" echo.
>>"%ENVFILE%" echo USE_CLAUDE_APP=true
>>"%ENVFILE%" echo TRELLO_READ_ONLY=true
>>"%ENVFILE%" echo TRELLO_CACHE_ENABLED=true
>>"%ENVFILE%" echo TRELLO_SYNC_ON_START=true
>>"%ENVFILE%" echo TRELLO_SYNC_INTERVAL_SECONDS=900
echo.
echo        Saved to trello\.env

:haveenv

REM ---------------------------------------------------------------- environment
echo  [3/5] Creating the Python environment (this takes a minute)...
if not exist "%PY%" (
    "%PYEXE%" %PYARG% -m venv "%VENV%" || goto :failed
)
"%PY%" -m pip install --quiet --upgrade pip >nul 2>&1
"%PY%" -m pip install --quiet -e "%APP%" || goto :failed
echo        Dependencies installed.

REM ---------------------------------------------------------------- self test
echo  [4/5] Checking the connector starts and can reach Trello...
"%PY%" "%APP%\selftest.py"
if errorlevel 1 goto :failed

REM ---------------------------------------------------------------- register
echo  [5/5] Registering with the ChatGPT app...
"%PY%" "%APP%\setup_codex.py" || goto :failed

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
echo   Then ask ChatGPT:  "Give me an overview of my Trello account."
echo.
echo   The first answer may take about 90 seconds while it indexes
echo   your boards. After that it is instant.
echo.
pause
exit /b 0

:nopython
echo.
echo  [X] Python 3.12 or 3.13 is needed and could not be installed automatically.
echo.
echo      Install it by hand from:
echo         https://www.python.org/downloads/release/python-3130/
echo.
echo      IMPORTANT: on the first installer screen, tick
echo         [x] Add python.exe to PATH
echo.
echo      Then run install.bat again.
echo.
pause
exit /b 1

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
