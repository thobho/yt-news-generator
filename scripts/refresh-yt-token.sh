#!/usr/bin/env bash
# Regenerate YouTube OAuth2 token.
# Opens browser for Google consent flow, saves new token.
#
# Usage: ./scripts/refresh-yt-token.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== YouTube Token Refresh ==="

# Activate venv
if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
else
  echo "Error: venv not found. Run ./scripts/dev.sh first."
  exit 1
fi

# Remove old token
rm -f credentials/token.json
echo "Old token removed."
echo "Opening browser for authentication..."
echo ""

# Authenticate and verify
python3 -c "
import sys
sys.path.insert(0, 'src')
from upload_youtube import authenticate
from googleapiclient.discovery import build

creds = authenticate()
youtube = build('youtube', 'v3', credentials=creds)
response = youtube.channels().list(part='snippet,id', mine=True).execute()

print()
print('Authenticated channel:')
for ch in response.get('items', []):
    print(f'  {ch[\"snippet\"][\"title\"]} (ID: {ch[\"id\"]})')
print()
print('Token saved to: credentials/token.json')
print()
print('Next step: update GitHub secret YT_TOKEN with:')
print('  cat credentials/token.json')
"
