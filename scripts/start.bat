@echo off
REM Twitch Miner Backend API - Development Startup Script
REM =====================================================
REM Usage: start.bat [--create-admin]

echo.
echo ==========================================
echo Twitch Miner Backend API - Development
echo ==========================================
echo.

REM Check for flags
set CREATE_ADMIN=false
if "%~1"=="--create-admin" set CREATE_ADMIN=true

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
echo Creating virtual environment at: %CD%\venv ...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment. Is Python installed?
    exit /b 1
)
set VENV_PATH=venv
echo Virtual environment created successfully.

:venv_found
echo Using virtual environment: %VENV_PATH%

set PYTHON=%VENV_PATH%\Scripts\python.exe
set PIP=%VENV_PATH%\Scripts\pip.exe

REM Check if main.py exists
if not exist "main.py" (
    echo ERROR: main.py not found. Are you in the project root?
    exit /b 1
)

REM Create data directory if it doesn't exist
if not exist "data" (
    echo Creating data directory...
    mkdir data
)

REM Install/update API dependencies
echo Installing API dependencies...
%PIP% install --no-cache-dir -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install API dependencies
    exit /b 1
)

REM Install TwitchChannelPointsMiner dependencies
if defined MINER_REPO_PATH (
    if exist "%MINER_REPO_PATH%\requirements.txt" (
        echo Installing TwitchChannelPointsMiner dependencies from: %MINER_REPO_PATH%
        %PIP% install --no-cache-dir -r "%MINER_REPO_PATH%\requirements.txt"
        if errorlevel 1 (
            echo ERROR: Failed to install TwitchChannelPointsMiner dependencies
            exit /b 1
        )
    )
) else if exist "twitch-miner\requirements.txt" (
    echo Installing TwitchChannelPointsMiner dependencies from: twitch-miner\
    %PIP% install --no-cache-dir -r twitch-miner\requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install TwitchChannelPointsMiner dependencies
        exit /b 1
    )
) else (
    echo WARNING: No TwitchChannelPointsMiner requirements found
)

REM Check if database exists, if not initialize it
if not exist "data\app.db" (
    echo.
    echo Database not found. Initializing...
    if "%CREATE_ADMIN%"=="true" (
        %PYTHON% setup.py --create-admin
    ) else (
        %PYTHON% setup.py
    )
    if errorlevel 1 (
        echo ERROR: Failed to initialize database
        exit /b 1
    )
) else if "%CREATE_ADMIN%"=="true" (
    echo.
    echo Creating admin user...
    %PYTHON% setup.py --create-admin
)

echo.
echo Starting API server with hot-reload...
echo Server: http://localhost:8000
echo API Docs: Check DOCS_URL in .env (default: /docs)
echo.
echo Press Ctrl+C to stop the server
echo ==========================================
echo.

REM Start the API with hot-reload for development
%PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

exit /b %ERRORLEVEL%
