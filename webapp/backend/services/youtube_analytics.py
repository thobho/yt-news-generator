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
    logger.info("Fetching YouTube stats from API for video: %s", video_id)
    analytics = get_youtube_analytics_service()

    # Get stats from video publish date to today
    # Use a wide date range to capture all data
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")

    try:
        response = analytics.reports().query(
            ids="channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched,averageViewPercentage,likes,comments,shares,subscribersGained",
            filters=f"video=={video_id}",
        ).execute()
        
        logger.debug("YouTube API raw response for %s: %s", video_id, response)
    except Exception as e:
        logger.error("YouTube Analytics API query failed for %s: %s", video_id, e)
        raise

    # Parse response
    rows = response.get("rows", [])
    if not rows:
        logger.info("No stats rows returned from API for video: %s", video_id)
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

    logger.info("Parsed stats for %s: views=%s, likes=%s", video_id, stats.get('views'), stats.get('likes'))
    return stats


def get_or_fetch_stats(run_id: str, force: bool = False, max_age_hours: Optional[int] = None) -> Optional[dict]:
    """
    Get cached stats or fetch fresh from YouTube Analytics API.

    Args:
        run_id: Run ID (e.g., 'run_2026-01-25_16-46-47')
        force: If True, fetch fresh stats even if cached
        max_age_hours: If provided, fetch fresh stats if cached ones are older than this

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
            
            # Check age if requested
            if max_age_hours is not None:
                fetched_at_str = cached.get("fetched_at")
                if fetched_at_str:
                    fetched_at = datetime.fromisoformat(fetched_at_str)
                    # Handle timezone-naive vs timezone-aware
                    if fetched_at.tzinfo is None:
                        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                    
                    age = datetime.now(timezone.utc) - fetched_at
                    if age < timedelta(hours=max_age_hours):
                        logger.debug("Using cached stats for run %s (age: %s)", run_id, age)
                        return cached
                    else:
                        logger.info("Cached stats for %s are too old (%s hours), refreshing", run_id, age.total_seconds() / 3600)
                else:
                    logger.info("Cached stats for %s have no timestamp, refreshing", run_id)
            else:
                logger.debug("Using cached stats for run %s (no max_age check)", run_id)
                return cached
        except (json.JSONDecodeError, Exception) as e:
            logger.debug("Error reading cached stats for %s: %s", run_id, e)
            pass

    # Check if credentials exist before trying to fetch
    if not TOKEN_PATH.exists():
        logger.warning("YouTube token missing, skipping stats fetch for %s", run_id)
        return None

    # Fetch fresh stats
    try:
        stats = fetch_video_stats(video_id)
    except Exception as e:
        logger.error("Failed to fetch stats for video %s in run %s: %s", video_id, run_id, e)
        return None # Return None instead of raising to allow process to continue

    result = {
        "video_id": video_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
    }

    # Cache the result
    run_storage.write_text(stats_path, json.dumps(result, indent=2))
    logger.info("Successfully fetched and cached fresh stats for video %s in run %s", video_id, run_id)

    return result
