#!/bin/bash
set -euo pipefail

info() { echo "$*"; }
warn() { echo "WARNING: $*"; }
die() { echo "ERROR: $*"; exit 1; }
has_cmd() { command -v "$1" >/dev/null 2>&1; }

on_interrupt() {
    echo ""
    info "Beende API ..."
}

trap on_interrupt INT TERM

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

print_header() {
    echo ""
    echo "======================================"
    echo "Twitch Miner Backend API - Production"
    echo "======================================"
    echo ""
}

kill_existing_listener() {
    has_cmd lsof || return 0
    local pids
    pids="$(lsof -ti:8000 -sTCP:LISTEN || true)"
    [[ -z "$pids" ]] && return 0

    info "Killing existing processes on port 8000: $pids"
    kill -9 $pids || true
    sleep 1
}

update_repo_if_git() {
    [[ -d .git ]] || return 0
    local branch
    branch="$(git rev-parse --abbrev-ref HEAD)"
    info "Updating repository on branch: $branch"
    git fetch --prune origin
    git pull --ff-only origin "$branch"
}

load_env_file() {
    [[ -f .env ]] || return 0
    set -a
    source .env
    set +a
}

select_venv_path() {
    local candidates=("${VENV_PATH:-}" "$PROJECT_ROOT/venv" "$SCRIPT_DIR/venv")
    local candidate
    for candidate in "${candidates[@]}"; do
        [[ -n "$candidate" && -d "$candidate" ]] && { echo "$candidate"; return 0; }
    done

    die "Virtual environment not found. Checked: VENV_PATH, $PROJECT_ROOT/venv, $SCRIPT_DIR/venv"
}

configure_python_tools() {
    local venv_path="$1"
    if [[ -d "$venv_path/Scripts" ]]; then
        PYTHON="$venv_path/Scripts/python"
        PIP="$venv_path/Scripts/pip"
    else
        PYTHON="$venv_path/bin/python"
        PIP="$venv_path/bin/pip"
    fi

    [[ -x "$PYTHON" ]] || die "Python executable not found in venv: $PYTHON"
    [[ -x "$PIP" ]] || die "Pip executable not found in venv: $PIP"
}

install_requirements() {
    local req_file="$1"
    local label="$2"
    info "Installing $label dependencies from: $req_file"
    "$PIP" install --no-cache-dir -r "$req_file"
}

resolve_worker_count() {
    if [[ -n "${UVICORN_WORKERS:-}" ]]; then
        echo "$UVICORN_WORKERS"
        return 0
    fi

    local cpu_count
    cpu_count="$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo 0)"
    [[ "$cpu_count" =~ ^[0-9]+$ ]] || cpu_count=0

    if [[ "$cpu_count" -le 0 ]]; then
        echo "2"
    else
        echo $((cpu_count * 2 + 1))
    fi
}

main() {
    print_header
    kill_existing_listener

    cd "$PROJECT_ROOT"
    update_repo_if_git
    load_env_file

    VENV_PATH="$(select_venv_path)"
    info "Using virtual environment: $VENV_PATH"
    configure_python_tools "$VENV_PATH"

    [[ -f "main.py" ]] || die "main.py not found. Are you in the project root?"
    mkdir -p data

    install_requirements "requirements.txt" "API"

    if [[ -n "${MINER_REPO_PATH:-}" && -f "${MINER_REPO_PATH}/requirements.txt" ]]; then
        install_requirements "${MINER_REPO_PATH}/requirements.txt" "TwitchChannelPointsMiner"
    elif [[ -f "twitch-miner/requirements.txt" ]]; then
        install_requirements "twitch-miner/requirements.txt" "TwitchChannelPointsMiner"
    else
        warn "No TwitchChannelPointsMiner requirements found"
    fi

    if [[ ! -f "data/app.db" ]]; then
        info "Database not found. Initializing with admin user..."
        "$PYTHON" setup.py --create-admin
    fi

    info "Running database migrations (single-run before workers start)..."
    "$PYTHON" -m alembic upgrade head

    # In multi-worker mode, avoid running migrations again in every worker process
    export RUN_MIGRATIONS_ON_STARTUP="${RUN_MIGRATIONS_ON_STARTUP:-false}"

    HOST="${API_HOST:-0.0.0.0}"
    PORT="${API_PORT:-8000}"
    LOG_LEVEL="${UVICORN_LOG_LEVEL:-info}"
    WORKERS="$(resolve_worker_count)"
    [[ "$WORKERS" =~ ^[0-9]+$ && "$WORKERS" -ge 1 ]] || WORKERS=1

    if [[ "$WORKERS" -gt 1 && -f "data/app.db" ]]; then
        warn "Multi-worker with SQLite can hit write-lock bottlenecks. For higher load, prefer PostgreSQL."
    fi

    echo ""
    info "Starting API server on ${HOST}:${PORT} with ${WORKERS} worker(s)..."
    info "Press Ctrl+C to stop the server"
    echo ""

    set +e
    "$PYTHON" -m uvicorn main:app \
        --host "$HOST" \
        --port "$PORT" \
        --workers "$WORKERS" \
        --log-level "$LOG_LEVEL" \
        --access-log
    local exit_code=$?
    set -e

    return "$exit_code"
}

main "$@"
