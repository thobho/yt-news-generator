#!/usr/bin/env bash
# Regenerate YouTube OAuth2 token.
# Opens browser for Google consent flow, saves new token.
#
# Usage: ./scripts/refresh-yt-token.sh [tenant]
#   tenant: pl (default) or us

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

TENANT="${1:-pl}"
CREDS_DIR="credentials/${TENANT}"

echo "=== YouTube Token Refresh (tenant: ${TENANT}) ==="

# Activate venv
if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
else
  echo "Error: venv not found. Run ./scripts/dev.sh first."
  exit 1
fi

# Remove old token
rm -f "${CREDS_DIR}/token.json"
echo "Old token removed."
echo "Opening browser for authentication..."
echo ""

# Authenticate and verify
python3 -c "
import sys
sys.path.insert(0, 'webapp/backend')
from publishing.youtube import authenticate
from googleapiclient.discovery import build

creds_dir = 'credentials/${TENANT}'
creds = authenticate(creds_dir)
youtube = build('youtube', 'v3', credentials=creds)
response = youtube.channels().list(part='snippet,id', mine=True).execute()

print()
print('Authenticated channel:')
for ch in response.get('items', []):
    print(f'  {ch[\"snippet\"][\"title\"]} (ID: {ch[\"id\"]})')
print()
print(f'Token saved to: {creds_dir}/token.json')
print()
print('Next step: update GitHub secret YT_TOKEN with:')
print(f'  cat {creds_dir}/token.json')
"
