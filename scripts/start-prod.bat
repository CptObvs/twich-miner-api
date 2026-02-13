@echo off
REM Twitch Miner Backend API - Production Startup Script
REM =====================================================
REM Requires: Python 3.11+

echo.
echo ==========================================
echo Twitch Miner Backend API - Production
echo ==========================================
echo.

REM Navigate to project root (one level up from scripts/)
cd /d "%~dp0\.."

REM Load VENV_PATH from .env if it exists
set VENV_PATH=
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if "%%A"=="VENV_PATH" set VENV_PATH=%%B
    )
)

REM Find virtual environment
REM Priority: VENV_PATH (from .env) > PROJECT_ROOT\venv > SCRIPT_DIR\venv
if defined VENV_PATH (
    if exist "%VENV_PATH%\Scripts\python.exe" goto :venv_found
)
if exist "venv\Scripts\python.exe" (
    set VENV_PATH=venv
    goto :venv_found
)
if exist "%~dp0venv\Scripts\python.exe" (
    set VENV_PATH=%~dp0venv
    goto :venv_found
)

echo ERROR: Virtual environment not found!
echo Expected locations:
echo   1. Path from VENV_PATH in .env
echo   2. %CD%\venv
echo   3. %~dp0venv
echo.
echo Create one with: python -m venv venv
exit /b 1

:venv_found
echo Using virtual environment: %VENV_PATH%

set PYTHON=%VENV_PATH%\Scripts\python.exe
set PIP=%VENV_PATH%\Scripts\pip.exe

REM Check if main.py exists
if not exist "main.py" (
    echo ERROR: main.py not found. Run this script from the project root.
    exit /b 1
)

REM Create data directory if it doesn't exist
if not exist "data" (
    echo Creating data directory...
    mkdir data
)

REM Install/update production dependencies
echo Installing dependencies...
%PIP% install --no-cache-dir -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    exit /b 1
)

REM Install TwitchChannelPointsMiner dependencies
if defined MINER_REPO_PATH (
    if exist "%MINER_REPO_PATH%\requirements.txt" (
        echo Installing TwitchChannelPointsMiner dependencies from: %MINER_REPO_PATH%
        %PIP% install --no-cache-dir -r "%MINER_REPO_PATH%\requirements.txt"
    )
) else if exist "twitch-miner\requirements.txt" (
    echo Installing TwitchChannelPointsMiner dependencies from: twitch-miner\
    %PIP% install --no-cache-dir -r twitch-miner\requirements.txt
)

echo.
echo Starting API server on 0.0.0.0:8000...
echo Press Ctrl+C to stop the server
echo.

REM Start uvicorn with production settings
%PYTHON% -m uvicorn main:app ^
    --host 0.0.0.0 ^
    --port 8000 ^
    --workers 4 ^
    --access-log

exit /b %ERRORLEVEL%
