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
export TENANT

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
python3 - <<'PYEOF'
import sys
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

import os
TENANT = os.environ.get("TENANT", "pl")
creds_dir = Path("credentials") / TENANT
token_path = creds_dir / "token.json"
client_secrets_path = creds_dir / "client_secrets.json"

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

creds = None
if token_path.exists():
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not client_secrets_path.exists():
            print(f"Error: {client_secrets_path} not found.")
            sys.exit(1)
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), SCOPES)
        creds = flow.run_local_server(port=0)

    creds_dir.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())

youtube = build("youtube", "v3", credentials=creds)
response = youtube.channels().list(part="snippet,id", mine=True).execute()

print()
print("Authenticated channel:")
for ch in response.get("items", []):
    print(f'  {ch["snippet"]["title"]} (ID: {ch["id"]})')
print()
print(f"Token saved to: {token_path}")
print()
print("Next step: update GitHub secret YT_TOKEN with:")
print(f"  cat {token_path}")
PYEOF
