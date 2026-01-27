#!/bin/bash
#
# Sync local changes to existing EC2 instance
# Usage: ./sync-ec2.sh [IP_ADDRESS]
#

set -e

KEY_PATH="credentials/yt-news-generator-key.pem"
PUBLIC_IP="${1:-100.53.141.50}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "Syncing to EC2: $PUBLIC_IP"
echo "========================================"

# Check key exists
if [ ! -f "$KEY_PATH" ]; then
  echo "ERROR: Key file not found: $KEY_PATH"
  exit 1
fi

# Sync project files
echo ""
echo "Copying files..."
rsync -avz --progress \
  --exclude 'node_modules' \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude '.git' \
  --exclude 'credentials' \
  --exclude '*.pem' \
  --exclude 'output' \
  -e "ssh -i $KEY_PATH -o StrictHostKeyChecking=no" \
  "$SCRIPT_DIR/" ubuntu@"$PUBLIC_IP":/home/ubuntu/yt-news-generator/

# Restart the webapp
echo ""
echo "Restarting webapp..."
ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no ubuntu@"$PUBLIC_IP" << 'REMOTE_SCRIPT'
cd /home/ubuntu/yt-news-generator
source .env
source venv/bin/activate

# Kill existing server
pkill -f uvicorn 2>/dev/null || true
sleep 1

# Start new server
nohup python -m uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000 > /tmp/webapp.log 2>&1 &
sleep 2

if pgrep -f uvicorn > /dev/null; then
  echo "Webapp restarted!"
else
  echo "ERROR: Webapp failed to start"
  cat /tmp/webapp.log
  exit 1
fi
REMOTE_SCRIPT

echo ""
echo "========================================"
echo "SYNC COMPLETE!"
echo "========================================"
echo "Webapp: http://${PUBLIC_IP}:8000"
echo ""
