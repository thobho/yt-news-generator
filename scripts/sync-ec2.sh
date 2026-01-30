#!/bin/bash
#
# Sync local changes to existing EC2 instance
# - Builds frontend locally
# - Copies all credentials
# - Installs dependencies
# - Sets up swap if needed
# Usage: ./sync-ec2.sh [IP_ADDRESS]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
KEY_PATH="$PROJECT_ROOT/credentials/yt-news-generator-key.pem"
PUBLIC_IP="${1:-54.166.188.230}"

echo "========================================"
echo "Syncing to EC2: $PUBLIC_IP"
echo "========================================"

# Check key exists
if [ ! -f "$KEY_PATH" ]; then
  echo "ERROR: Key file not found: $KEY_PATH"
  exit 1
fi

# ==========================================
# Build frontend locally
# ==========================================
echo ""
echo "Building frontend locally..."
cd "$PROJECT_ROOT/webapp/frontend"

if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies..."
  npm install
fi

npm run build

rm -rf "$PROJECT_ROOT/webapp/backend/static"
cp -r dist "$PROJECT_ROOT/webapp/backend/static"
echo "Frontend built!"

cd "$PROJECT_ROOT"

# ==========================================
# Copy all credentials
# ==========================================
echo ""
echo "Copying credentials..."

# Create credentials directory on remote
ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no ubuntu@"$PUBLIC_IP" \
  "mkdir -p /home/ubuntu/yt-news-generator/credentials"

# Copy env.production as .env
if [ -f "$PROJECT_ROOT/credentials/env.production" ]; then
  scp -i "$KEY_PATH" -o StrictHostKeyChecking=no \
    "$PROJECT_ROOT/credentials/env.production" \
    ubuntu@"$PUBLIC_IP":/home/ubuntu/yt-news-generator/.env
  echo "  - env.production -> .env"
fi

# Copy YouTube OAuth credentials
if [ -f "$PROJECT_ROOT/credentials/client_secrets.json" ]; then
  scp -i "$KEY_PATH" -o StrictHostKeyChecking=no \
    "$PROJECT_ROOT/credentials/client_secrets.json" \
    ubuntu@"$PUBLIC_IP":/home/ubuntu/yt-news-generator/credentials/
  echo "  - client_secrets.json"
fi

if [ -f "$PROJECT_ROOT/credentials/token.json" ]; then
  scp -i "$KEY_PATH" -o StrictHostKeyChecking=no \
    "$PROJECT_ROOT/credentials/token.json" \
    ubuntu@"$PUBLIC_IP":/home/ubuntu/yt-news-generator/credentials/
  echo "  - token.json"
fi

echo "Credentials copied!"

# ==========================================
# Sync project files
# ==========================================
echo ""
echo "Copying project files..."
rsync -avz --progress \
  --exclude 'node_modules' \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude '.git' \
  --exclude 'credentials' \
  --exclude '*.pem' \
  --exclude 'output' \
  --exclude 'storage' \
  -e "ssh -i $KEY_PATH -o StrictHostKeyChecking=no" \
  "$PROJECT_ROOT/" ubuntu@"$PUBLIC_IP":/home/ubuntu/yt-news-generator/

# ==========================================
# Install dependencies and restart
# ==========================================
echo ""
echo "Installing dependencies and restarting..."

ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no ubuntu@"$PUBLIC_IP" << 'REMOTE_SCRIPT'
set -e
cd /home/ubuntu/yt-news-generator

# ---- Swap setup (for instances with < 2GB RAM) ----
TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
SWAP_TOTAL=$(free -m | awk '/^Swap:/{print $2}')
if [ "$TOTAL_MEM" -lt 2048 ] && [ "$SWAP_TOTAL" -lt 1024 ]; then
  echo "Low memory detected (${TOTAL_MEM}MB RAM, ${SWAP_TOTAL}MB swap). Setting up 2GB swap..."
  if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  else
    sudo swapon /swapfile 2>/dev/null || true
  fi
  echo "Swap ready: $(free -m | awk '/^Swap:/{print $2}')MB"
fi

# ---- Python dependencies ----
echo ""
echo "Installing Python dependencies..."
source venv/bin/activate
pip install -q -r requirements.txt
pip install -q -r webapp/backend/requirements.txt

# ---- NPM dependencies for Remotion ----
echo ""
echo "Installing Remotion dependencies..."
cd remotion
if [ ! -d "node_modules" ]; then
  npm install
else
  npm install --prefer-offline
fi
cd ..

# ---- Restart webapp ----
echo ""
echo "Restarting webapp..."
source .env
pkill -f uvicorn 2>/dev/null || true
sleep 1

nohup python -m uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000 > /tmp/webapp.log 2>&1 &
sleep 2

if pgrep -f uvicorn > /dev/null; then
  echo "Webapp restarted!"
  echo "Memory: $(free -m | awk '/^Mem:/{print $2}')MB RAM, $(free -m | awk '/^Swap:/{print $2}')MB swap"
else
  echo "ERROR: Webapp failed to start"
  tail -20 /tmp/webapp.log
  exit 1
fi
REMOTE_SCRIPT

echo ""
echo "========================================"
echo "SYNC COMPLETE!"
echo "========================================"
echo "Webapp: http://${PUBLIC_IP}:8000"
echo ""
