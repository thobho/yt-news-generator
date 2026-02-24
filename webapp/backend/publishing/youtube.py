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
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Union

from google.auth.transport.requests import Request

from ..core.logging_config import get_logger
from ..core.storage import StorageBackend
from ..core.storage_config import get_project_root

logger = get_logger(__name__)
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

try:
    import zoneinfo as _zoneinfo
    def _get_tz(name: str):
        return _zoneinfo.ZoneInfo(name)
except ImportError:
    from backports import zoneinfo as _zoneinfo
    def _get_tz(name: str):
        return _zoneinfo.ZoneInfo(name)

WARSAW_TZ = _get_tz("Europe/Warsaw")

PROJECT_ROOT = get_project_root()

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

PLAYLIST_TITLE = "Daily News"


def get_scheduled_publish_time(schedule_option: str = "evening", timezone_str: str = "Europe/Warsaw") -> str | None:
    """
    Calculate publish time in the given timezone based on schedule option.

    Args:
        schedule_option: One of:
            - "now" - Publish immediately (returns None, video will be public)
            - "evening" - Random time between 18:00-20:00 today in the tenant timezone,
                          or next day if already past 19:00
        timezone_str: IANA timezone name (e.g. "Europe/Warsaw", "America/New_York")

    Returns ISO 8601 string in UTC for the YouTube API, or None for immediate publish.
    """
    import random
    from datetime import timezone

    if schedule_option == "now":
        return None

    # "evening" - random time between 18:00 and 20:00 in the tenant's local timezone
    local_tz = _get_tz(timezone_str)
    now = datetime.now(local_tz)

    # Random minutes within 18:00-20:00 range (0-120 minutes from 18:00)
    random_minutes = random.randint(0, 120)

    # Start with 18:00 today
    publish_local = now.replace(hour=18, minute=0, second=0, microsecond=0)
    publish_local = publish_local + timedelta(minutes=random_minutes)

    # If it's already past 19:00, schedule for tomorrow
    if now.hour >= 19:
        publish_local = publish_local + timedelta(days=1)

    # Convert to UTC ISO 8601 format required by YouTube API
    publish_utc = publish_local.astimezone(timezone.utc)
    return publish_utc.strftime("%Y-%m-%dT%H:%M:%S.0Z")


def authenticate(credentials_dir: str = "credentials/pl") -> Credentials:
    """Authenticate with OAuth2, reusing cached token if available.

    Args:
        credentials_dir: Directory containing client_secrets.json and token.json.
    """
    creds_path = PROJECT_ROOT / credentials_dir
    token_path = creds_path / "token.json"
    client_secrets_path = creds_path / "client_secrets.json"

    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.debug("Refreshing expired credentials")
            creds.refresh(Request())
        else:
            if not client_secrets_path.exists():
                logger.error(
                    "Client secrets not found at %s. "
                    "Download OAuth 2.0 credentials from Google Cloud Console "
                    "and save as %s/client_secrets.json",
                    client_secrets_path,
                    credentials_dir,
                )
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets_path), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for next run
        creds_path.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return creds


def parse_yt_metadata(
    metadata_path: Union[Path, str],
    storage: StorageBackend = None
) -> dict:
    """
    Parse yt_metadata.md to extract title, description, and tags.

    Expected format:
        # 🎬 YouTube Metadata
        ## Tytuł
        <title>
        ## Opis
        <description with #hashtags>

    Args:
        metadata_path: Path to metadata file
        storage: Optional storage backend. If None, reads from local filesystem.
    """
    if storage is not None:
        content = storage.read_text(str(metadata_path))
    else:
        content = Path(metadata_path).read_text(encoding="utf-8")

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
    logger.info("Created playlist '%s': %s", title, response['id'])
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


def upload_video(youtube, video_path: Path, metadata: dict, publish_at: str | None) -> str:
    """Upload video to YouTube. Returns video ID.

    If publish_at is None, video is published immediately as public.
    Otherwise, video is private and scheduled to publish at the given time.
    """
    status = {
        "selfDeclaredMadeForKids": False,
    }

    if publish_at is None:
        # Publish immediately as public
        status["privacyStatus"] = "public"
    else:
        # Schedule for later
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata["tags"],
            "categoryId": "25",  # News & Politics
        },
        "status": status,
    }

    media = MediaFileUpload(
        str(video_path), mimetype="video/mp4", resumable=True, chunksize=10 * 1024 * 1024
    )

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    logger.info("Uploading video to YouTube...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.debug("Upload progress: %d%%", int(status.progress() * 100))

    video_id = response["id"]
    logger.info("Upload complete. Video ID: %s", video_id)
    return video_id


def delete_from_youtube(video_id: str, credentials_dir: str = "credentials/pl") -> None:
    """Delete a video from YouTube by its video ID."""
    logger.info("Deleting video from YouTube: %s", video_id)
    creds = authenticate(credentials_dir)
    youtube = build("youtube", "v3", credentials=creds)
    youtube.videos().delete(id=video_id).execute()
    logger.info("Video deleted from YouTube: %s", video_id)


def upload_to_youtube(
    video_path: Union[Path, str],
    metadata_path: Union[Path, str],
    storage: StorageBackend = None,
    schedule_option: str = "auto",
    credentials_dir: str = "credentials/pl",
    timezone_str: str = "Europe/Warsaw",
) -> tuple[str, str | None]:
    """
    Full upload pipeline: authenticate, parse metadata, upload, add to playlist.

    Args:
        video_path: Path/key to the video file (.mp4)
        metadata_path: Path/key to yt_metadata.md
        storage: Optional storage backend. If provided, downloads files from storage.
        schedule_option: One of "now" (publish immediately) or "evening" (random 18:00-20:00)
        timezone_str: IANA timezone name used for the "evening" window calculation

    Returns:
        Tuple of (video_id, publish_at). publish_at is None if published immediately.
    """
    # Validate files exist
    if storage is not None:
        if not storage.exists(str(video_path)):
            logger.error("Video not found: %s", video_path)
            sys.exit(1)
        if not storage.exists(str(metadata_path)):
            logger.error("Metadata not found: %s", metadata_path)
            sys.exit(1)
    else:
        if not Path(video_path).exists():
            logger.error("Video not found: %s", video_path)
            sys.exit(1)
        if not Path(metadata_path).exists():
            logger.error("Metadata not found: %s", metadata_path)
            sys.exit(1)

    metadata = parse_yt_metadata(metadata_path, storage)
    publish_at = get_scheduled_publish_time(schedule_option, timezone_str)

    logger.info("Title: %s", metadata['title'])
    logger.info("Tags: %s", ', '.join(metadata['tags']))
    if publish_at:
        logger.info("Scheduled publish: %s", publish_at)
    else:
        logger.info("Publishing immediately")

    creds = authenticate(credentials_dir)
    youtube = build("youtube", "v3", credentials=creds)

    # YouTube API needs a local file path
    if storage is not None:
        with storage.get_local_path(str(video_path)) as local_video:
            video_id = upload_video(youtube, local_video, metadata, publish_at)
    else:
        video_id = upload_video(youtube, Path(video_path), metadata, publish_at)

    # Add to DailyNews playlist
    playlist_id = find_or_create_playlist(youtube, PLAYLIST_TITLE)
    add_to_playlist(youtube, playlist_id, video_id)
    logger.info("Added to playlist '%s'", PLAYLIST_TITLE)

    if publish_at:
        logger.info("Video scheduled for %s: https://youtu.be/%s", publish_at, video_id)
    else:
        logger.info("Video published: https://youtu.be/%s", video_id)

    return video_id, publish_at


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Upload video to YouTube")
    parser.add_argument("video", type=Path, help="Path to video file")
    parser.add_argument("metadata", type=Path, help="Path to yt_metadata.md")
    parser.add_argument(
        "--credentials-dir",
        default="credentials/pl",
        help="Directory containing client_secrets.json and token.json (default: credentials/pl)",
    )
    args = parser.parse_args()

    upload_to_youtube(args.video, args.metadata, credentials_dir=args.credentials_dir)
