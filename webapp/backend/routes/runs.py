import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse

from ..models import RunSummary, RunDetail, RunFiles, WorkflowState, YouTubeUpload
from ..services import pipeline

# Add src to path for storage imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from storage_config import get_output_storage, get_run_storage, get_storage_dir, is_s3_enabled
from storage import S3StorageBackend

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Path to output directory (uses storage directory)
def _get_output_dir() -> Path:
    return get_storage_dir() / "output"


def parse_run_timestamp(run_id: str) -> Optional[datetime]:
    """Parse timestamp from run ID like 'run_2026-01-25_16-46-47'."""
    try:
        timestamp_str = run_id.replace("run_", "")
        return datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


def get_run_status_for_run(run_id: str) -> str:
    """Determine run status based on available files."""
    run_storage = get_run_storage(run_id)

    has_video = run_storage.exists("video.mp4")
    has_audio = run_storage.exists("audio.mp3")
    has_dialogue = run_storage.exists("dialogue.json")
    has_images = run_storage.exists("images/images.json")

    if has_video and has_audio and has_dialogue and has_images:
        return "complete"
    elif has_dialogue:
        return "partial"
    else:
        return "error"


def get_run_status(run_path: Path) -> str:
    """Determine run status based on available files (legacy local interface)."""
    return get_run_status_for_run(run_path.name)


def get_run_title_for_run(run_id: str) -> Optional[str]:
    """Extract title from yt_metadata.md or dialogue.json."""
    run_storage = get_run_storage(run_id)

    if run_storage.exists("yt_metadata.md"):
        try:
            content = run_storage.read_text("yt_metadata.md")
            for line in content.split("\n"):
                if line.startswith("## Tytu"):
                    lines = content.split("\n")
                    idx = lines.index(line)
                    if idx + 1 < len(lines):
                        return lines[idx + 1].strip()
        except Exception:
            pass

    if run_storage.exists("dialogue.json"):
        try:
            content = run_storage.read_text("dialogue.json")
            data = json.loads(content)
            return data.get("hook") or data.get("topic_id")
        except (json.JSONDecodeError, Exception):
            pass

    return None


def get_run_title(run_path: Path) -> Optional[str]:
    """Extract title from yt_metadata.md or dialogue.json (legacy interface)."""
    return get_run_title_for_run(run_path.name)


def count_images_for_run(run_id: str) -> int:
    """Count images in run directory."""
    run_storage = get_run_storage(run_id)

    if not run_storage.exists("images/images.json"):
        return 0

    try:
        content = run_storage.read_text("images/images.json")
        data = json.loads(content)
        return len(data.get("images", []))
    except Exception:
        return 0


def count_images(run_path: Path) -> int:
    """Count scene images in run directory (legacy interface)."""
    return count_images_for_run(run_path.name)


def _build_run_summary_from_keys(run_id: str, run_keys: set[str], title: Optional[str] = None) -> RunSummary | None:
    """Build RunSummary using pre-fetched key list (avoids extra S3 calls)."""
    timestamp = parse_run_timestamp(run_id)
    if not timestamp:
        return None

    has_video = "video.mp4" in run_keys
    has_audio = "audio.mp3" in run_keys
    has_images = "images/images.json" in run_keys
    has_dialogue = "dialogue.json" in run_keys
    has_youtube = "yt_upload.json" in run_keys

    # Determine status from available files
    if has_video and has_audio and has_dialogue and has_images:
        status = "complete"
    elif has_dialogue:
        status = "partial"
    else:
        status = "error"

    # Count images from key list instead of reading JSON
    image_count = sum(1 for k in run_keys if k.startswith("images/") and k.endswith(".png"))

    return RunSummary(
        id=run_id,
        timestamp=timestamp,
        title=title,
        status=status,
        has_video=has_video,
        has_audio=has_audio,
        has_images=has_images,
        has_youtube=has_youtube,
        image_count=image_count,
    )


@router.get("", response_model=list[RunSummary])
async def list_runs():
    """List all runs with summary info."""
    output_storage = get_output_storage()
    runs = []

    if is_s3_enabled():
        # List ALL keys once (single S3 call)
        all_keys = await asyncio.to_thread(output_storage.list_keys, "")

        # Group keys by run_id
        run_keys_map: dict[str, set[str]] = {}
        for key in all_keys:
            parts = key.split("/", 1)
            if parts and parts[0].startswith("run_"):
                run_id = parts[0]
                if run_id not in run_keys_map:
                    run_keys_map[run_id] = set()
                if len(parts) > 1:
                    run_keys_map[run_id].add(parts[1])

        # Identify runs that need titles fetched
        runs_needing_titles = [
            run_id for run_id, keys in run_keys_map.items()
            if "yt_metadata.md" in keys or "dialogue.json" in keys
        ]

        # Fetch all titles in parallel
        titles = await asyncio.gather(*[
            asyncio.to_thread(get_run_title_for_run, run_id)
            for run_id in runs_needing_titles
        ])
        title_map = dict(zip(runs_needing_titles, titles))

        # Build summaries using cached keys and pre-fetched titles
        for run_id, run_keys in run_keys_map.items():
            title = title_map.get(run_id)
            run_summary = _build_run_summary_from_keys(run_id, run_keys, title=title)
            if run_summary:
                runs.append(run_summary)
    else:
        # Local filesystem mode
        if not _get_output_dir().exists():
            return []

        # Collect valid run directories
        run_entries = [
            entry for entry in _get_output_dir().iterdir()
            if entry.is_dir() and entry.name.startswith("run_") and parse_run_timestamp(entry.name)
        ]

        # Fetch all titles in parallel
        titles = await asyncio.gather(*[
            asyncio.to_thread(get_run_title_for_run, entry.name)
            for entry in run_entries
        ])

        for entry, title in zip(run_entries, titles):
            timestamp = parse_run_timestamp(entry.name)
            run_storage = get_run_storage(entry.name)
            run_summary = RunSummary(
                id=entry.name,
                timestamp=timestamp,
                title=title,
                status=get_run_status_for_run(entry.name),
                has_video=run_storage.exists("video.mp4"),
                has_audio=run_storage.exists("audio.mp3"),
                has_images=run_storage.exists("images/images.json"),
                has_youtube=run_storage.exists("yt_upload.json"),
                image_count=count_images_for_run(entry.name),
            )
            runs.append(run_summary)

    # Sort by timestamp, newest first
    runs.sort(key=lambda r: r.timestamp, reverse=True)
    return runs


def _read_json_file(run_storage, key: str) -> Optional[dict]:
    """Read and parse a JSON file from storage."""
    try:
        if run_storage.exists(key):
            return json.loads(run_storage.read_text(key))
    except (json.JSONDecodeError, Exception):
        pass
    return None


def _read_text_file(run_storage, key: str) -> Optional[str]:
    """Read a text file from storage."""
    try:
        if run_storage.exists(key):
            return run_storage.read_text(key)
    except Exception:
        pass
    return None


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: str):
    """Get full run details."""
    run_storage = get_run_storage(run_id)

    # Check if run exists by looking for any file
    exists_seed = await asyncio.to_thread(run_storage.exists, "seed.json")
    exists_dialogue = await asyncio.to_thread(run_storage.exists, "dialogue.json")

    if not exists_seed and not exists_dialogue:
        # For local mode, also check if directory exists
        if not is_s3_enabled():
            run_path = _get_output_dir() / run_id
            if not run_path.exists() or not run_path.is_dir():
                raise HTTPException(status_code=404, detail="Run not found")
        else:
            raise HTTPException(status_code=404, detail="Run not found")

    timestamp = parse_run_timestamp(run_id)
    if not timestamp:
        raise HTTPException(status_code=400, detail="Invalid run ID format")

    # Fetch all files in parallel
    (
        dialogue,
        timeline,
        images_meta,
        yt_metadata,
        yt_upload_data,
        news_data,
    ) = await asyncio.gather(
        asyncio.to_thread(_read_json_file, run_storage, "dialogue.json"),
        asyncio.to_thread(_read_json_file, run_storage, "timeline.json"),
        asyncio.to_thread(_read_json_file, run_storage, "images/images.json"),
        asyncio.to_thread(_read_text_file, run_storage, "yt_metadata.md"),
        asyncio.to_thread(_read_json_file, run_storage, "yt_upload.json"),
        asyncio.to_thread(_read_json_file, run_storage, "downloaded_news_data.json"),
    )

    # Parse yt_upload
    yt_upload = None
    if yt_upload_data:
        try:
            yt_upload = YouTubeUpload(**yt_upload_data)
        except (ValueError, Exception):
            pass

    # Check for media files in parallel
    exists_video, exists_audio = await asyncio.gather(
        asyncio.to_thread(run_storage.exists, "video.mp4"),
        asyncio.to_thread(run_storage.exists, "audio.mp3"),
    )

    # Build file URLs
    files = RunFiles()
    if exists_video:
        files.video = f"/api/runs/{run_id}/video"
    if exists_audio:
        files.audio = f"/api/runs/{run_id}/audio"

    # Get image files from images metadata
    if images_meta:
        for img in images_meta.get("images", []):
            if img.get("file"):
                files.images.append(f"/api/runs/{run_id}/images/{img['file']}")

    # Get workflow state
    workflow_state = await asyncio.to_thread(pipeline.get_workflow_state_for_run, run_id)

    return RunDetail(
        id=run_id,
        timestamp=timestamp,
        dialogue=dialogue,
        timeline=timeline,
        images=images_meta,
        yt_metadata=yt_metadata,
        yt_upload=yt_upload,
        news_data=news_data,
        files=files,
        workflow=WorkflowState(**workflow_state),
    )


@router.get("/{run_id}/video")
async def get_video(run_id: str):
    """Serve video file."""
    run_storage = get_run_storage(run_id)

    if not run_storage.exists("video.mp4"):
        raise HTTPException(status_code=404, detail="Video not found")

    if is_s3_enabled() and isinstance(run_storage, S3StorageBackend):
        # Return presigned URL redirect for S3
        presigned_url = run_storage.generate_presigned_url("video.mp4", expires_in=3600)
        return RedirectResponse(url=presigned_url)
    else:
        # Local file
        video_path = _get_output_dir() / run_id / "video.mp4"
        return FileResponse(video_path, media_type="video/mp4")


@router.get("/{run_id}/audio")
async def get_audio(run_id: str):
    """Serve audio file."""
    run_storage = get_run_storage(run_id)

    if not run_storage.exists("audio.mp3"):
        raise HTTPException(status_code=404, detail="Audio not found")

    if is_s3_enabled() and isinstance(run_storage, S3StorageBackend):
        # Return presigned URL redirect for S3
        presigned_url = run_storage.generate_presigned_url("audio.mp3", expires_in=3600)
        return RedirectResponse(url=presigned_url)
    else:
        # Local file
        audio_path = _get_output_dir() / run_id / "audio.mp3"
        return FileResponse(audio_path, media_type="audio/mpeg")


@router.get("/{run_id}/images/{filename}")
async def get_image(run_id: str, filename: str):
    """Serve image files."""
    # Validate filename to prevent path traversal
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    run_storage = get_run_storage(run_id)
    image_key = f"images/{filename}"

    if not run_storage.exists(image_key):
        raise HTTPException(status_code=404, detail="Image not found")

    if is_s3_enabled() and isinstance(run_storage, S3StorageBackend):
        # Return presigned URL redirect for S3
        presigned_url = run_storage.generate_presigned_url(image_key, expires_in=3600)
        return RedirectResponse(url=presigned_url)
    else:
        # Local file
        image_path = _get_output_dir() / run_id / "images" / filename
        return FileResponse(image_path, media_type="image/png")


@router.delete("/{run_id}")
async def delete_run(run_id: str):
    """Delete an entire run and all its files."""
    run_storage = get_run_storage(run_id)

    # Check if run exists
    if not run_storage.exists("seed.json") and not run_storage.exists("dialogue.json"):
        if not is_s3_enabled():
            run_path = _get_output_dir() / run_id
            if not run_path.exists():
                raise HTTPException(status_code=404, detail="Run not found")
        else:
            raise HTTPException(status_code=404, detail="Run not found")

    result = pipeline.delete_run_for_run(run_id)
    return {"status": "deleted", **result}
