"""
Analytics routes for YouTube video statistics.
"""

import asyncio
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks

from ..models import AnalyticsRun, YouTubeStats

# Add src to path for storage imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from logging_config import get_logger
from storage_config import get_output_storage, get_run_storage, is_s3_enabled

logger = get_logger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def parse_run_timestamp(run_id: str) -> Optional[datetime]:
    """Parse timestamp from run ID like 'run_2026-01-25_16-46-47'."""
    try:
        timestamp_str = run_id.replace("run_", "")
        return datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


def _read_json_file(run_storage, key: str) -> Optional[dict]:
    """Read and parse a JSON file from storage."""
    try:
        if run_storage.exists(key):
            return json.loads(run_storage.read_text(key))
    except (json.JSONDecodeError, Exception):
        pass
    return None


def _get_run_title(run_storage) -> Optional[str]:
    """Extract title from yt_metadata.md."""
    try:
        if run_storage.exists("yt_metadata.md"):
            content = run_storage.read_text("yt_metadata.md")
            for line in content.split("\n"):
                if line.startswith("## Tytu"):
                    lines = content.split("\n")
                    idx = lines.index(line)
                    if idx + 1 < len(lines):
                        return lines[idx + 1].strip()
    except Exception:
        pass
    return None


def _extract_episode_number(title: Optional[str]) -> Optional[int]:
    """Extract episode number from title like 'Episode #123: ...'."""
    if not title:
        return None
    match = re.search(r"#(\d+)", title)
    if match:
        return int(match.group(1))
    return None


def _is_older_than_48_hours(publish_at: Optional[str]) -> bool:
    """Check if publish_at timestamp is older than 48 hours."""
    if not publish_at:
        return True  # If no publish time, assume it's published

    try:
        # Parse ISO format
        publish_dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - publish_dt) > timedelta(hours=48)
    except (ValueError, Exception):
        return True


async def _build_analytics_run(run_id: str) -> Optional[AnalyticsRun]:
    """Build AnalyticsRun from run storage."""
    run_storage = get_run_storage(run_id)

    # Check for YT upload
    yt_upload = await asyncio.to_thread(_read_json_file, run_storage, "yt_upload.json")
    if not yt_upload:
        return None

    video_id = yt_upload.get("video_id")
    if not video_id:
        return None

    publish_at = yt_upload.get("publish_at")

    # Only include videos older than 48 hours
    if not _is_older_than_48_hours(publish_at):
        return None

    timestamp = parse_run_timestamp(run_id)
    if not timestamp:
        return None

    # Get title
    title = await asyncio.to_thread(_get_run_title, run_storage)

    # Get cached stats if available
    yt_stats = await asyncio.to_thread(_read_json_file, run_storage, "yt_stats.json")

    stats = None
    stats_fetched_at = None
    if yt_stats:
        stats_data = yt_stats.get("stats", {})
        stats = YouTubeStats(
            views=stats_data.get("views", 0),
            estimatedMinutesWatched=stats_data.get("estimatedMinutesWatched", 0.0),
            averageViewPercentage=stats_data.get("averageViewPercentage", 0.0),
            likes=stats_data.get("likes", 0),
            comments=stats_data.get("comments", 0),
            shares=stats_data.get("shares", 0),
            subscribersGained=stats_data.get("subscribersGained", 0),
        )
        stats_fetched_at = yt_stats.get("fetched_at")

    return AnalyticsRun(
        id=run_id,
        timestamp=timestamp,
        title=title,
        video_id=video_id,
        url=f"https://youtu.be/{video_id}",
        publish_at=publish_at,
        episode_number=_extract_episode_number(title),
        stats=stats,
        stats_fetched_at=stats_fetched_at,
    )


@router.get("/runs", response_model=list[AnalyticsRun])
async def list_analytics_runs():
    """List runs with YouTube uploads older than 48 hours, with cached stats."""
    output_storage = get_output_storage()
    runs = []

    if is_s3_enabled():
        # List all keys once
        all_keys = await asyncio.to_thread(output_storage.list_keys, "")

        # Find runs with yt_upload.json
        run_ids_with_yt = set()
        for key in all_keys:
            parts = key.split("/", 1)
            if len(parts) > 1 and parts[0].startswith("run_") and parts[1] == "yt_upload.json":
                run_ids_with_yt.add(parts[0])

        # Build analytics runs in parallel
        analytics_runs = await asyncio.gather(*[
            _build_analytics_run(run_id) for run_id in run_ids_with_yt
        ])
        runs = [r for r in analytics_runs if r is not None]
    else:
        # Local filesystem
        from storage_config import get_storage_dir
        output_dir = get_storage_dir() / "output"
        if not output_dir.exists():
            return []

        run_entries = [
            entry for entry in output_dir.iterdir()
            if entry.is_dir() and entry.name.startswith("run_")
        ]

        # Build analytics runs in parallel
        analytics_runs = await asyncio.gather(*[
            _build_analytics_run(entry.name) for entry in run_entries
        ])
        runs = [r for r in analytics_runs if r is not None]

    # Sort by timestamp, newest first
    runs.sort(key=lambda r: r.timestamp, reverse=True)

    return runs


@router.post("/runs/{run_id}/refresh", response_model=AnalyticsRun)
async def refresh_run_stats(run_id: str):
    """Fetch fresh stats from YouTube Analytics API for a specific run."""
    from ..services.youtube_analytics import get_or_fetch_stats

    # Verify run exists and has YT upload
    run_storage = get_run_storage(run_id)
    if not run_storage.exists("yt_upload.json"):
        raise HTTPException(status_code=404, detail="Run not found or no YouTube upload")

    try:
        # Force refresh stats
        await asyncio.to_thread(get_or_fetch_stats, run_id, True)
    except Exception as e:
        logger.error("Failed to refresh stats for run %s: %s", run_id, e)
        raise HTTPException(status_code=500, detail=str(e))

    # Return updated run
    result = await _build_analytics_run(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Failed to build analytics run")

    return result


async def _refresh_all_stats():
    """Background task to refresh stats for all eligible runs."""
    from ..services.youtube_analytics import get_or_fetch_stats

    output_storage = get_output_storage()

    if is_s3_enabled():
        all_keys = output_storage.list_keys("")
        run_ids_with_yt = set()
        for key in all_keys:
            parts = key.split("/", 1)
            if len(parts) > 1 and parts[0].startswith("run_") and parts[1] == "yt_upload.json":
                run_ids_with_yt.add(parts[0])
    else:
        from storage_config import get_storage_dir
        output_dir = get_storage_dir() / "output"
        run_ids_with_yt = set()
        if output_dir.exists():
            for entry in output_dir.iterdir():
                if entry.is_dir() and entry.name.startswith("run_"):
                    run_storage = get_run_storage(entry.name)
                    if run_storage.exists("yt_upload.json"):
                        run_ids_with_yt.add(entry.name)

    for run_id in run_ids_with_yt:
        run_storage = get_run_storage(run_id)
        yt_upload = _read_json_file(run_storage, "yt_upload.json")
        if yt_upload and _is_older_than_48_hours(yt_upload.get("publish_at")):
            try:
                get_or_fetch_stats(run_id, force=True)
                logger.info("Refreshed stats for run %s", run_id)
            except Exception as e:
                logger.error("Failed to refresh stats for run %s: %s", run_id, e)


@router.post("/refresh-all")
async def refresh_all_stats(background_tasks: BackgroundTasks):
    """Start background task to refresh stats for all eligible runs."""
    background_tasks.add_task(_refresh_all_stats)
    return {"status": "started", "message": "Refreshing stats for all eligible runs in background"}
