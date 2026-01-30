"""
Workflow routes - API endpoints for pipeline actions.
"""

import sys
import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

# Add src to path for logging and storage
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from logging_config import get_logger
from storage_config import get_run_storage, get_storage_dir, is_s3_enabled

logger = get_logger(__name__)

from ..services import pipeline

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

def _get_output_dir() -> Path:
    return get_storage_dir() / "output"


# Request/Response models

class CreateSeedRequest(BaseModel):
    news_text: str


class CreateSeedResponse(BaseModel):
    run_id: str
    seed_path: str


class DialogueUpdateRequest(BaseModel):
    dialogue: dict[str, Any]


class ImagesUpdateRequest(BaseModel):
    images: dict[str, Any]


class YouTubeUploadRequest(BaseModel):
    schedule_option: str = "auto"  # "8:00", "18:00", "1hour", or "auto"


class WorkflowState(BaseModel):
    current_step: str
    has_seed: bool
    has_dialogue: bool
    has_audio: bool
    has_images: bool
    has_video: bool
    has_yt_metadata: bool
    can_generate_dialogue: bool
    can_edit_dialogue: bool
    can_generate_audio: bool
    can_generate_video: bool
    can_upload: bool
    can_delete_youtube: bool = False
    # Regeneration options
    can_drop_audio: bool = False
    can_drop_images: bool = False
    can_drop_video: bool = False


class TaskStatus(BaseModel):
    status: str  # running | completed | error
    message: str | None = None
    result: dict[str, Any] | None = None


# In-memory task tracking (simple approach, could use Redis/DB for production)
_tasks: dict[str, TaskStatus] = {}


def get_running_tasks_for_run(run_id: str) -> dict[str, TaskStatus]:
    """Get all running tasks for a specific run."""
    result = {}
    for task_id, status in _tasks.items():
        if task_id.startswith(f"{run_id}:") and status.status == "running":
            # Extract task type from task_id (e.g., "run_xxx:dialogue" -> "dialogue")
            task_type = task_id.split(":", 1)[1] if ":" in task_id else task_id
            result[task_type] = status
    return result


def get_all_running_tasks() -> dict[str, dict[str, Any]]:
    """Get all running tasks across all runs."""
    result = {}
    for task_id, status in _tasks.items():
        if status.status == "running":
            parts = task_id.split(":", 1)
            if len(parts) == 2:
                run_id, task_type = parts
                if run_id not in result:
                    result[run_id] = {}
                result[run_id][task_type] = {
                    "status": status.status,
                    "message": status.message
                }
    return result


def validate_run_exists(run_id: str) -> None:
    """Validate that a run exists (in S3 or local filesystem)."""
    run_storage = get_run_storage(run_id)

    # Check if any file exists for this run
    if not run_storage.exists("seed.json") and not run_storage.exists("dialogue.json"):
        if not is_s3_enabled():
            run_dir = _get_output_dir() / run_id
            if not run_dir.exists():
                raise HTTPException(status_code=404, detail="Run not found")
        else:
            raise HTTPException(status_code=404, detail="Run not found")


def get_run_dir(run_id: str) -> Path:
    """Get run directory path (for backward compatibility)."""
    run_dir = _get_output_dir() / run_id
    if not is_s3_enabled() and not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return run_dir


# Endpoints

@router.post("/create-seed", response_model=CreateSeedResponse)
async def create_seed(request: CreateSeedRequest):
    """Create a new seed and run directory."""
    if not request.news_text.strip():
        raise HTTPException(status_code=400, detail="News text cannot be empty")

    run_id, seed_key = pipeline.create_seed(request.news_text)

    return CreateSeedResponse(
        run_id=run_id,
        seed_path=seed_key
    )


@router.get("/{run_id}/state", response_model=WorkflowState)
async def get_workflow_state(run_id: str):
    """Get current workflow state for a run."""
    validate_run_exists(run_id)
    state = pipeline.get_workflow_state_for_run(run_id)
    return WorkflowState(**state)


@router.post("/{run_id}/generate-dialogue")
async def generate_dialogue(run_id: str, background_tasks: BackgroundTasks):
    """Start dialogue generation (runs in background)."""
    validate_run_exists(run_id)

    task_id = f"{run_id}:dialogue"
    if task_id in _tasks and _tasks[task_id].status == "running":
        raise HTTPException(status_code=409, detail="Task already running")

    _tasks[task_id] = TaskStatus(status="running", message="Generating dialogue...")

    def run_task():
        try:
            result = pipeline.generate_dialogue_for_run(run_id)
            _tasks[task_id] = TaskStatus(
                status="completed",
                message="Dialogue generated successfully",
                result={"dialogue": result}
            )
        except Exception as e:
            logger.exception("Dialogue generation failed")
            _tasks[task_id] = TaskStatus(
                status="error",
                message=str(e)
            )

    background_tasks.add_task(run_task)

    return {"task_id": task_id, "status": "started"}


@router.put("/{run_id}/dialogue")
async def update_dialogue(run_id: str, request: DialogueUpdateRequest):
    """Update dialogue JSON for a run."""
    validate_run_exists(run_id)

    state = pipeline.get_workflow_state_for_run(run_id)
    if not state["can_edit_dialogue"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot edit dialogue at this stage"
        )

    result = pipeline.update_dialogue_for_run(run_id, request.dialogue)
    return {"status": "updated", "dialogue": result}


@router.post("/{run_id}/generate-audio")
async def generate_audio(run_id: str, background_tasks: BackgroundTasks):
    """Start audio generation (runs in background)."""
    validate_run_exists(run_id)

    state = pipeline.get_workflow_state_for_run(run_id)
    if not state["can_generate_audio"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot generate audio at this stage"
        )

    task_id = f"{run_id}:audio"
    if task_id in _tasks and _tasks[task_id].status == "running":
        raise HTTPException(status_code=409, detail="Task already running")

    _tasks[task_id] = TaskStatus(status="running", message="Generating audio...")

    def run_task():
        try:
            # Generate audio
            pipeline.generate_audio_for_run(run_id)

            # Also generate images after audio
            _tasks[task_id] = TaskStatus(
                status="running",
                message="Generating images..."
            )
            pipeline.generate_images_for_run(run_id)

            # Generate YT metadata
            _tasks[task_id] = TaskStatus(
                status="running",
                message="Generating YouTube metadata..."
            )
            pipeline.generate_yt_metadata_for_run(run_id)

            _tasks[task_id] = TaskStatus(
                status="completed",
                message="Audio, images, and metadata generated successfully"
            )
        except Exception as e:
            logger.exception("Audio/images generation failed")
            _tasks[task_id] = TaskStatus(
                status="error",
                message=str(e)
            )

    background_tasks.add_task(run_task)

    return {"task_id": task_id, "status": "started"}


@router.post("/{run_id}/generate-video")
async def generate_video(run_id: str, background_tasks: BackgroundTasks):
    """Start video generation (runs in background)."""
    validate_run_exists(run_id)

    state = pipeline.get_workflow_state_for_run(run_id)
    if not state["can_generate_video"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot generate video at this stage"
        )

    task_id = f"{run_id}:video"
    if task_id in _tasks and _tasks[task_id].status == "running":
        raise HTTPException(status_code=409, detail="Task already running")

    _tasks[task_id] = TaskStatus(status="running", message="Rendering video...")

    def run_task():
        try:
            video_key = pipeline.generate_video_for_run(run_id)
            _tasks[task_id] = TaskStatus(
                status="completed",
                message="Video rendered successfully",
                result={"video_path": video_key}
            )
        except Exception as e:
            logger.exception("Video generation failed")
            _tasks[task_id] = TaskStatus(
                status="error",
                message=str(e)
            )

    background_tasks.add_task(run_task)

    return {"task_id": task_id, "status": "started"}


@router.post("/{run_id}/upload-youtube")
async def upload_youtube(
    run_id: str,
    background_tasks: BackgroundTasks,
    request: YouTubeUploadRequest = None
):
    """Upload video to YouTube (runs in background)."""
    validate_run_exists(run_id)

    state = pipeline.get_workflow_state_for_run(run_id)
    if not state["can_upload"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot upload at this stage"
        )

    task_id = f"{run_id}:youtube"
    if task_id in _tasks and _tasks[task_id].status == "running":
        raise HTTPException(status_code=409, detail="Task already running")

    schedule_option = request.schedule_option if request else "auto"
    _tasks[task_id] = TaskStatus(status="running", message="Uploading to YouTube...")

    def run_task():
        try:
            result = pipeline.upload_to_youtube_for_run(run_id, schedule_option=schedule_option)
            _tasks[task_id] = TaskStatus(
                status="completed",
                message="Uploaded to YouTube successfully",
                result=result
            )
        except Exception as e:
            logger.exception("YouTube upload failed")
            _tasks[task_id] = TaskStatus(
                status="error",
                message=str(e)
            )

    background_tasks.add_task(run_task)

    return {"task_id": task_id, "status": "started"}


@router.delete("/{run_id}/youtube")
async def delete_youtube(run_id: str):
    """Delete uploaded video from YouTube and remove upload record."""
    validate_run_exists(run_id)

    state = pipeline.get_workflow_state_for_run(run_id)
    if not state["can_delete_youtube"]:
        raise HTTPException(
            status_code=400,
            detail="No YouTube upload to delete"
        )

    result = pipeline.delete_youtube_for_run(run_id)
    return {"status": "deleted", **result}


@router.get("/task/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Get status of a background task."""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    return _tasks[task_id]


@router.get("/tasks/running")
async def get_all_running():
    """Get all running tasks across all runs (for list view)."""
    return get_all_running_tasks()


@router.get("/{run_id}/tasks/running")
async def get_run_running_tasks(run_id: str):
    """Get running tasks for a specific run."""
    tasks = get_running_tasks_for_run(run_id)
    return {
        "run_id": run_id,
        "tasks": {k: {"status": v.status, "message": v.message} for k, v in tasks.items()}
    }


@router.put("/{run_id}/images")
async def update_images(run_id: str, request: ImagesUpdateRequest):
    """Update images.json for a run."""
    validate_run_exists(run_id)

    result = pipeline.update_images_metadata_for_run(run_id, request.images)
    return {"status": "updated", "images": result}


@router.post("/{run_id}/regenerate-image/{image_id}")
async def regenerate_image(run_id: str, image_id: str, background_tasks: BackgroundTasks):
    """Regenerate a single image by ID."""
    validate_run_exists(run_id)

    task_id = f"{run_id}:image:{image_id}"
    if task_id in _tasks and _tasks[task_id].status == "running":
        raise HTTPException(status_code=409, detail="Task already running")

    _tasks[task_id] = TaskStatus(status="running", message=f"Regenerating {image_id}...")

    def run_task():
        try:
            result = pipeline.regenerate_single_image_for_run(run_id, image_id)
            _tasks[task_id] = TaskStatus(
                status="completed",
                message=f"Image {image_id} regenerated successfully",
                result=result
            )
        except Exception as e:
            logger.exception("Image regeneration failed")
            _tasks[task_id] = TaskStatus(
                status="error",
                message=str(e)
            )

    background_tasks.add_task(run_task)

    return {"task_id": task_id, "status": "started"}


@router.delete("/{run_id}/audio")
async def drop_audio(run_id: str):
    """Delete audio and timeline for a run, allowing regeneration."""
    validate_run_exists(run_id)

    state = pipeline.get_workflow_state_for_run(run_id)
    if not state["can_drop_audio"]:
        raise HTTPException(
            status_code=400,
            detail="No audio to drop"
        )

    result = pipeline.drop_audio_for_run(run_id)
    return {"status": "dropped", **result}


@router.delete("/{run_id}/video")
async def drop_video(run_id: str):
    """Delete video for a run, allowing regeneration."""
    validate_run_exists(run_id)

    state = pipeline.get_workflow_state_for_run(run_id)
    if not state["can_drop_video"]:
        raise HTTPException(
            status_code=400,
            detail="No video to drop"
        )

    result = pipeline.drop_video_for_run(run_id)
    return {"status": "dropped", **result}


@router.delete("/{run_id}/images")
async def drop_images(run_id: str):
    """Delete all images for a run, allowing regeneration."""
    validate_run_exists(run_id)

    state = pipeline.get_workflow_state_for_run(run_id)
    if not state["can_drop_images"]:
        raise HTTPException(
            status_code=400,
            detail="No images to drop"
        )

    result = pipeline.drop_images_for_run(run_id)
    return {"status": "dropped", **result}
