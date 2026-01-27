#!/bin/bash
#
# YT News Generator - Development Runner
# Runs backend and frontend with hot-reloading
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

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

mkdir -p output

# Function to cleanup background processes
cleanup() {
    log_info "Shutting down..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start backend
log_info "Starting backend on http://localhost:8000"
uvicorn webapp.backend.main:app --reload --port 8000 &
BACKEND_PID=$!

# Start frontend
log_info "Starting frontend on http://localhost:5173"
(cd webapp/frontend && npm run dev) &
FRONTEND_PID=$!

log_info "Development servers running. Press Ctrl+C to stop."
log_info "Open http://localhost:5173 in your browser"

# Wait for processes
wait
