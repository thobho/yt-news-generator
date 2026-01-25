#!/usr/bin/env python3
"""
Upload video to YouTube with scheduled publishing and playlist management.

Prerequisites:
    1. Enable YouTube Data API v3 in Google Cloud Console
    2. Create OAuth 2.0 credentials (Desktop app)
    3. Save client secrets as credentials/client_secrets.json
    4. First run opens browser for consent → stores token at credentials/token.json
"""

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

try:
    import zoneinfo
    WARSAW_TZ = zoneinfo.ZoneInfo("Europe/Warsaw")
except ImportError:
    from backports.zoneinfo import ZoneInfo
    WARSAW_TZ = ZoneInfo("Europe/Warsaw")

PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_DIR = PROJECT_ROOT / "credentials"
CLIENT_SECRETS_PATH = CREDENTIALS_DIR / "client_secrets.json"
TOKEN_PATH = CREDENTIALS_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

PLAYLIST_TITLE = "Daily News"


def get_scheduled_publish_time() -> str:
    """
    Calculate next publish time in Europe/Warsaw timezone.

    Rules:
        - If now < 8:00 → schedule today 8:00
        - If 8:00 ≤ now < 16:00 → schedule today 16:00
        - If now ≥ 16:00 → schedule tomorrow 8:00

    Returns ISO 8601 string in UTC for the YouTube API.
    """
    now = datetime.now(WARSAW_TZ)

    if now.hour < 8:
        publish_local = now.replace(hour=8, minute=0, second=0, microsecond=0)
    elif now.hour < 16:
        publish_local = now.replace(hour=16, minute=0, second=0, microsecond=0)
    else:
        tomorrow = now + timedelta(days=1)
        publish_local = tomorrow.replace(hour=8, minute=0, second=0, microsecond=0)

    # Convert to UTC ISO 8601 format required by YouTube API
    from datetime import timezone
    publish_utc = publish_local.astimezone(timezone.utc)
    return publish_utc.strftime("%Y-%m-%dT%H:%M:%S.0Z")


def authenticate() -> Credentials:
    """Authenticate with OAuth2, reusing cached token if available."""
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRETS_PATH.exists():
                print(
                    f"Error: Client secrets not found at {CLIENT_SECRETS_PATH}\n"
                    "Download OAuth 2.0 credentials from Google Cloud Console\n"
                    "and save as credentials/client_secrets.json",
                    file=sys.stderr,
                )
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRETS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for next run
        CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return creds


def parse_yt_metadata(metadata_path: Path) -> dict:
    """
    Parse yt_metadata.md to extract title, description, and tags.

    Expected format:
        # 🎬 YouTube Metadata
        ## Tytuł
        <title>
        ## Opis
        <description with #hashtags>
    """
    content = metadata_path.read_text(encoding="utf-8")

    # Extract title (text between "## Tytuł" and "## Opis")
    title_match = re.search(r"## Tytuł\s*\n(.+?)(?=\n## )", content, re.DOTALL)
    title = title_match.group(1).strip() if title_match else "Untitled"

    # Extract description (everything after "## Opis")
    desc_match = re.search(r"## Opis\s*\n(.+)", content, re.DOTALL)
    description = desc_match.group(1).strip() if desc_match else ""

    # Extract hashtags as tags
    tags = re.findall(r"#(\w+)", description)

    return {"title": title, "description": description, "tags": tags}


def find_or_create_playlist(youtube, title: str) -> str:
    """Find existing playlist by title, or create a new one. Returns playlist ID."""
    # Search existing playlists
    request = youtube.playlists().list(part="snippet", mine=True, maxResults=50)
    response = request.execute()

    for item in response.get("items", []):
        if item["snippet"]["title"] == title:
            return item["id"]

    # Create new playlist
    request = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": "Daily news discussions"},
            "status": {"privacyStatus": "public"},
        },
    )
    response = request.execute()
    print(f"Created playlist '{title}': {response['id']}", file=sys.stderr)
    return response["id"]


def add_to_playlist(youtube, playlist_id: str, video_id: str):
    """Add a video to a playlist."""
    youtube.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        },
    ).execute()


def upload_video(youtube, video_path: Path, metadata: dict, publish_at: str) -> str:
    """Upload video to YouTube as private with scheduled publish time. Returns video ID."""
    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata["tags"],
            "categoryId": "25",  # News & Politics
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path), mimetype="video/mp4", resumable=True, chunksize=10 * 1024 * 1024
    )

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print("Uploading video...", file=sys.stderr)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Upload progress: {int(status.progress() * 100)}%", file=sys.stderr)

    video_id = response["id"]
    print(f"Upload complete. Video ID: {video_id}", file=sys.stderr)
    return video_id


def upload_to_youtube(video_path: Path, metadata_path: Path) -> str:
    """
    Full upload pipeline: authenticate, parse metadata, upload, add to playlist.

    Args:
        video_path: Path to the video file (.mp4)
        metadata_path: Path to yt_metadata.md

    Returns:
        The YouTube video ID
    """
    if not video_path.exists():
        print(f"Error: Video not found: {video_path}", file=sys.stderr)
        sys.exit(1)
    if not metadata_path.exists():
        print(f"Error: Metadata not found: {metadata_path}", file=sys.stderr)
        sys.exit(1)

    metadata = parse_yt_metadata(metadata_path)
    publish_at = get_scheduled_publish_time()

    print(f"Title: {metadata['title']}", file=sys.stderr)
    print(f"Tags: {', '.join(metadata['tags'])}", file=sys.stderr)
    print(f"Scheduled publish: {publish_at}", file=sys.stderr)

    creds = authenticate()
    youtube = build("youtube", "v3", credentials=creds)

    video_id = upload_video(youtube, video_path, metadata, publish_at)

    # Add to DailyNews playlist
    playlist_id = find_or_create_playlist(youtube, PLAYLIST_TITLE)
    add_to_playlist(youtube, playlist_id, video_id)
    print(f"Added to playlist '{PLAYLIST_TITLE}'", file=sys.stderr)

    print(
        f"\nVideo scheduled for {publish_at}\n"
        f"https://youtu.be/{video_id}",
        file=sys.stderr,
    )

    return video_id


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Upload video to YouTube")
    parser.add_argument("video", type=Path, help="Path to video file")
    parser.add_argument("metadata", type=Path, help="Path to yt_metadata.md")
    args = parser.parse_args()

    upload_to_youtube(args.video, args.metadata)
