#!/bin/bash
# Twitch Miner Backend API - Development Startup Script
# Usage: ./start.sh [--create-admin]

echo ""
echo "=========================================="
echo "Twitch Miner Backend API - Development"
echo "=========================================="
echo ""

# Check for flags
CREATE_ADMIN=false
if [ "$1" = "--create-admin" ]; then
    CREATE_ADMIN=true
fi

# Navigate to project root (one level up from scripts/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$PROJECT_ROOT"

# Load environment variables from .env first (to read VENV_PATH if configured)
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Find virtual environment
# Priority: VENV_PATH (from .env) > PROJECT_ROOT/venv > SCRIPT_DIR/venv
if [ -n "$VENV_PATH" ] && [ -d "$VENV_PATH" ]; then
    VENV_PATH="$VENV_PATH"
elif [ -d "$PROJECT_ROOT/venv" ]; then
    VENV_PATH="$PROJECT_ROOT/venv"
elif [ -d "$SCRIPT_DIR/venv" ]; then
    VENV_PATH="$SCRIPT_DIR/venv"
else
    echo "ERROR: Virtual environment not found!"
    echo "Expected locations:"
    echo "  1. Path from VENV_PATH in .env"
    echo "  2. $PROJECT_ROOT/venv"
    echo "  3. $SCRIPT_DIR/venv"
    echo ""
    echo "Create one with: python -m venv venv"
    exit 1
fi

echo "Using virtual environment: $VENV_PATH"

# Set Python and pip paths from venv (handle Windows vs Linux layout)
if [ -d "$VENV_PATH/Scripts" ]; then
    PYTHON="$VENV_PATH/Scripts/python"
    PIP="$VENV_PATH/Scripts/pip"
else
    PYTHON="$VENV_PATH/bin/python"
    PIP="$VENV_PATH/bin/pip"
fi

# Check if main.py exists
if [ ! -f "main.py" ]; then
    echo "ERROR: main.py not found. Are you in the project root?"
    exit 1
fi

# Create data directory if it doesn't exist
if [ ! -d "data" ]; then
    echo "Creating data directory..."
    mkdir -p data
fi

# Install/update API dependencies
echo "Installing API dependencies..."
$PIP install --no-cache-dir -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install API dependencies"
    exit 1
fi

# Install TwitchChannelPointsMiner dependencies
# First try MINER_REPO_PATH if configured, then fallback to local twitch-miner/
if [ -n "$MINER_REPO_PATH" ] && [ -d "$MINER_REPO_PATH" ] && [ -f "$MINER_REPO_PATH/requirements.txt" ]; then
    echo "Installing TwitchChannelPointsMiner dependencies from: $MINER_REPO_PATH"
    $PIP install --no-cache-dir -r "$MINER_REPO_PATH/requirements.txt"
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install TwitchChannelPointsMiner dependencies"
        exit 1
    fi
elif [ -f "twitch-miner/requirements.txt" ]; then
    echo "Installing TwitchChannelPointsMiner dependencies from: twitch-miner/"
    $PIP install --no-cache-dir -r twitch-miner/requirements.txt
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install TwitchChannelPointsMiner dependencies"
        exit 1
    fi
else
    echo "WARNING: No TwitchChannelPointsMiner requirements found"
fi

# Check if database exists, if not initialize it
if [ ! -f "data/app.db" ]; then
    echo ""
    echo "Database not found. Initializing..."
    if [ "$CREATE_ADMIN" = true ]; then
        $PYTHON setup.py --create-admin
    else
        $PYTHON setup.py
    fi
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to initialize database"
        exit 1
    fi
elif [ "$CREATE_ADMIN" = true ]; then
    echo ""
    echo "Creating admin user..."
    $PYTHON setup.py --create-admin
    if [ $? -ne 0 ]; then
        echo "WARNING: Failed to create admin user (might already exist)"
    fi
fi

echo ""
echo "Starting API server with hot-reload..."
echo "Server: http://localhost:8000"
echo "API Docs: Check DOCS_URL in .env (default: /docs)"
echo ""
echo "Press Ctrl+C to stop the server"
echo "=========================================="
echo ""

# Start the API with hot-reload for development
$PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

exit $?
