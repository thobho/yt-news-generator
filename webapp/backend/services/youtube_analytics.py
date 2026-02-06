"""
YouTube Analytics API service for fetching video statistics.

Uses YouTube Analytics API v2 to fetch metrics like views, watch time,
likes, comments, and shares.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Add src to path for storage imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from logging_config import get_logger
from storage_config import get_run_storage, get_project_root

logger = get_logger(__name__)

CREDENTIALS_DIR = get_project_root() / "credentials"
TOKEN_PATH = CREDENTIALS_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def get_youtube_analytics_service():
    """Get authenticated YouTube Analytics API service."""
    if not TOKEN_PATH.exists():
        raise RuntimeError("YouTube credentials not found. Run scripts/refresh-yt-token.sh first.")

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError("YouTube credentials expired. Delete credentials/token.json and run scripts/refresh-yt-token.sh")

    return build("youtubeAnalytics", "v2", credentials=creds)


def fetch_video_stats(video_id: str) -> dict:
    """
    Fetch video statistics from YouTube Analytics API.

    Args:
        video_id: YouTube video ID

    Returns:
        Dict with stats: views, estimatedMinutesWatched, averageViewPercentage,
        likes, comments, shares
    """
    analytics = get_youtube_analytics_service()

    # Get stats from video publish date to today
    # Use a wide date range to capture all data
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")

    response = analytics.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        metrics="views,estimatedMinutesWatched,averageViewPercentage,likes,comments,shares,subscribersGained",
        filters=f"video=={video_id}",
    ).execute()

    # Parse response
    rows = response.get("rows", [])
    if not rows:
        return {
            "views": 0,
            "estimatedMinutesWatched": 0.0,
            "averageViewPercentage": 0.0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "subscribersGained": 0,
        }

    # First row contains the aggregated stats
    row = rows[0]
    column_headers = response.get("columnHeaders", [])

    stats = {}
    for i, header in enumerate(column_headers):
        name = header["name"]
        value = row[i] if i < len(row) else 0
        stats[name] = value

    return stats


def get_or_fetch_stats(run_id: str, force: bool = False) -> Optional[dict]:
    """
    Get cached stats or fetch fresh from YouTube Analytics API.

    Args:
        run_id: Run ID (e.g., 'run_2026-01-25_16-46-47')
        force: If True, fetch fresh stats even if cached

    Returns:
        Dict with video_id, fetched_at, and stats, or None if no YT upload
    """
    run_storage = get_run_storage(run_id)

    # Check if this run has a YouTube upload
    if not run_storage.exists("yt_upload.json"):
        return None

    yt_upload = json.loads(run_storage.read_text("yt_upload.json"))
    video_id = yt_upload.get("video_id")
    if not video_id:
        return None

    stats_path = "yt_stats.json"

    # Check for cached stats
    if not force and run_storage.exists(stats_path):
        try:
            cached = json.loads(run_storage.read_text(stats_path))
            return cached
        except (json.JSONDecodeError, Exception):
            pass

    # Fetch fresh stats
    try:
        stats = fetch_video_stats(video_id)
    except Exception as e:
        logger.error("Failed to fetch stats for video %s: %s", video_id, e)
        raise

    result = {
        "video_id": video_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
    }

    # Cache the result
    run_storage.write_text(stats_path, json.dumps(result, indent=2))
    logger.info("Fetched and cached stats for video %s in run %s", video_id, run_id)

    return result
