#!/bin/bash
#
# YT News Generator - Production Runner
# Installs dependencies, builds frontend, and runs in production mode
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check required commands
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "$1 is not installed. Please install it first."
        exit 1
    fi
}

log_info "Checking required commands..."
check_command python3
check_command node
check_command npm

# Check required environment variables
check_env() {
    if [ -z "${!1}" ]; then
        log_error "Environment variable $1 is not set"
        return 1
    fi
}

log_info "Checking environment variables..."
MISSING_ENV=0

check_env "OPENAI_API_KEY" || MISSING_ENV=1
check_env "ELEVENLABS_API_KEY" || MISSING_ENV=1
check_env "PERPLEXITY_API_KEY" || MISSING_ENV=1
check_env "AUTH_PASSWORD" || MISSING_ENV=1

if [ $MISSING_ENV -eq 1 ]; then
    log_error "Missing required environment variables. See README.md for details."
    exit 1
fi

# Validate AUTH_PASSWORD is not too short
if [ ${#AUTH_PASSWORD} -lt 8 ]; then
    log_error "AUTH_PASSWORD must be at least 8 characters long"
    exit 1
fi

# Check Google OAuth credentials
if [ ! -f "credentials/client_secrets.json" ]; then
    log_warn "Google OAuth credentials not found at credentials/client_secrets.json"
    log_warn "YouTube upload feature will not work without this file."
fi

# ==========================================
# Python dependencies
# ==========================================

log_info "Setting up Python environment..."

if [ ! -d "venv" ]; then
    log_info "Creating Python virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

log_info "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
pip install --quiet -r webapp/backend/requirements.txt

# ==========================================
# Node.js dependencies - Remotion
# ==========================================

log_info "Installing Remotion dependencies..."
if [ ! -d "remotion/node_modules" ]; then
    (cd remotion && npm install)
else
    log_info "Remotion node_modules exists, skipping install"
fi

# ==========================================
# Node.js dependencies - Frontend
# ==========================================

log_info "Installing frontend dependencies..."
if [ ! -d "webapp/frontend/node_modules" ]; then
    (cd webapp/frontend && npm install)
else
    log_info "Frontend node_modules exists, skipping install"
fi

# ==========================================
# Build frontend
# ==========================================

log_info "Building frontend for production..."
(cd webapp/frontend && npm run build)

# Move build to backend static folder
STATIC_DIR="webapp/backend/static"
rm -rf "$STATIC_DIR"
mkdir -p "$STATIC_DIR"
cp -r webapp/frontend/dist/* "$STATIC_DIR/"

log_info "Frontend built and copied to $STATIC_DIR"

# ==========================================
# Create output directory
# ==========================================

mkdir -p output

# ==========================================
# Run production server
# ==========================================

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

log_info "Starting production server on http://${HOST}:${PORT}"
log_info "Press Ctrl+C to stop"

exec uvicorn webapp.backend.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers 1
