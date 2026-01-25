import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..models import RunSummary, RunDetail, RunFiles, WorkflowState, YouTubeUpload
from ..services import pipeline

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Path to output directory (relative to project root)
OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "output"


def parse_run_timestamp(run_id: str) -> Optional[datetime]:
    """Parse timestamp from run ID like 'run_2026-01-25_16-46-47'."""
    try:
        timestamp_str = run_id.replace("run_", "")
        return datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


def get_run_status(run_path: Path) -> str:
    """Determine run status based on available files."""
    has_video = (run_path / "video.mp4").exists()
    has_audio = (run_path / "audio.mp3").exists()
    has_dialogue = (run_path / "dialogue.json").exists()
    has_images = (run_path / "images").is_dir() and any(
        (run_path / "images").glob("scene_*.png")
    )

    if has_video and has_audio and has_dialogue and has_images:
        return "complete"
    elif has_dialogue:
        return "partial"
    else:
        return "error"


def get_run_title(run_path: Path) -> Optional[str]:
    """Extract title from yt_metadata.md or dialogue.json."""
    yt_metadata_path = run_path / "yt_metadata.md"
    if yt_metadata_path.exists():
        content = yt_metadata_path.read_text()
        for line in content.split("\n"):
            if line.startswith("## Tytu"):
                # Next non-empty line is the title
                lines = content.split("\n")
                idx = lines.index(line)
                if idx + 1 < len(lines):
                    return lines[idx + 1].strip()

    dialogue_path = run_path / "dialogue.json"
    if dialogue_path.exists():
        try:
            data = json.loads(dialogue_path.read_text())
            return data.get("hook") or data.get("topic_id")
        except json.JSONDecodeError:
            pass

    return None


def count_images(run_path: Path) -> int:
    """Count scene images in run directory."""
    images_dir = run_path / "images"
    if not images_dir.is_dir():
        return 0
    return len(list(images_dir.glob("scene_*.png")))


@router.get("", response_model=list[RunSummary])
async def list_runs():
    """List all runs with summary info."""
    if not OUTPUT_DIR.exists():
        return []

    runs = []
    for entry in OUTPUT_DIR.iterdir():
        if not entry.is_dir() or not entry.name.startswith("run_"):
            continue

        timestamp = parse_run_timestamp(entry.name)
        if not timestamp:
            continue

        run_summary = RunSummary(
            id=entry.name,
            timestamp=timestamp,
            title=get_run_title(entry),
            status=get_run_status(entry),
            has_video=(entry / "video.mp4").exists(),
            has_audio=(entry / "audio.mp3").exists(),
            has_images=(entry / "images").is_dir(),
            image_count=count_images(entry),
        )
        runs.append(run_summary)

    # Sort by timestamp, newest first
    runs.sort(key=lambda r: r.timestamp, reverse=True)
    return runs


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: str):
    """Get full run details."""
    run_path = OUTPUT_DIR / run_id

    if not run_path.exists() or not run_path.is_dir():
        raise HTTPException(status_code=404, detail="Run not found")

    timestamp = parse_run_timestamp(run_id)
    if not timestamp:
        raise HTTPException(status_code=400, detail="Invalid run ID format")

    # Load JSON files
    dialogue = None
    dialogue_path = run_path / "dialogue.json"
    if dialogue_path.exists():
        try:
            dialogue = json.loads(dialogue_path.read_text())
        except json.JSONDecodeError:
            pass

    timeline = None
    timeline_path = run_path / "timeline.json"
    if timeline_path.exists():
        try:
            timeline = json.loads(timeline_path.read_text())
        except json.JSONDecodeError:
            pass

    images_meta = None
    images_json_path = run_path / "images" / "images.json"
    if images_json_path.exists():
        try:
            images_meta = json.loads(images_json_path.read_text())
        except json.JSONDecodeError:
            pass

    yt_metadata = None
    yt_metadata_path = run_path / "yt_metadata.md"
    if yt_metadata_path.exists():
        yt_metadata = yt_metadata_path.read_text()

    yt_upload = None
    yt_upload_path = run_path / "yt_upload.json"
    if yt_upload_path.exists():
        try:
            yt_upload_data = json.loads(yt_upload_path.read_text())
            yt_upload = YouTubeUpload(**yt_upload_data)
        except (json.JSONDecodeError, ValueError):
            pass

    news_data = None
    news_data_path = run_path / "downloaded_news_data.json"
    if news_data_path.exists():
        try:
            news_data = json.loads(news_data_path.read_text())
        except json.JSONDecodeError:
            pass

    # Build file URLs
    files = RunFiles()
    if (run_path / "video.mp4").exists():
        files.video = f"/api/runs/{run_id}/video"
    if (run_path / "audio.mp3").exists():
        files.audio = f"/api/runs/{run_id}/audio"

    images_dir = run_path / "images"
    if images_dir.is_dir():
        for img in sorted(images_dir.glob("scene_*.png")):
            files.images.append(f"/api/runs/{run_id}/images/{img.name}")

    # Get workflow state
    workflow_state = pipeline.get_workflow_state(run_path)

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
    video_path = OUTPUT_DIR / run_id / "video.mp4"

    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")

    return FileResponse(video_path, media_type="video/mp4")


@router.get("/{run_id}/audio")
async def get_audio(run_id: str):
    """Serve audio file."""
    audio_path = OUTPUT_DIR / run_id / "audio.mp3"

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")

    return FileResponse(audio_path, media_type="audio/mpeg")


@router.get("/{run_id}/images/{filename}")
async def get_image(run_id: str, filename: str):
    """Serve image files."""
    # Validate filename to prevent path traversal
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    image_path = OUTPUT_DIR / run_id / "images" / filename

    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(image_path, media_type="image/png")
