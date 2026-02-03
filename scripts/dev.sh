#!/bin/bash
#
# YT News Generator - Development Runner
# Runs backend and frontend with hot-reloading using local storage.
#
# Before first run, sync S3 data:
#   ./scripts/dump-s3.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Force local storage for development
export STORAGE_BACKEND=local

# Check for local storage data
if [ ! -d "storage/data" ]; then
    log_warn "No local storage data found."
    log_warn "Run ./scripts/dump-s3.sh to sync data from S3 first."
    exit 1
fi

# Setup Python if needed
if [ ! -d "venv" ]; then
    log_info "Creating Python virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

log_info "Installing Python dependencies..."
pip install --quiet -r requirements.txt
pip install --quiet -r webapp/backend/requirements.txt

# Install frontend deps if needed
if [ ! -d "webapp/frontend/node_modules" ]; then
    log_info "Installing frontend dependencies..."
    (cd webapp/frontend && npm install)
fi

# Install remotion deps if needed
if [ ! -d "remotion/node_modules" ]; then
    log_info "Installing Remotion dependencies..."
    (cd remotion && npm install)
fi

# Ensure local storage directories exist
mkdir -p storage/data storage/output

# Function to cleanup background processes
cleanup() {
    log_info "Shutting down..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Allow host/port overrides to avoid IPv6 bind issues
DEV_HOST="${DEV_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

# Start backend
log_info "Starting backend on http://${DEV_HOST}:${BACKEND_PORT} (STORAGE_BACKEND=local)"
uvicorn webapp.backend.main:app --reload --host "${DEV_HOST}" --port "${BACKEND_PORT}" &
BACKEND_PID=$!

# Start frontend
log_info "Starting frontend on http://${DEV_HOST}:${FRONTEND_PORT}"
(cd webapp/frontend && npm run dev -- --host "${DEV_HOST}" --port "${FRONTEND_PORT}") &
FRONTEND_PID=$!

log_info "Development servers running. Press Ctrl+C to stop."
log_info "Open http://${DEV_HOST}:${FRONTEND_PORT} in your browser"

# Wait for processes
wait
