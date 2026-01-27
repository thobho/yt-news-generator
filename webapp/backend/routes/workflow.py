"""
Workflow routes - API endpoints for pipeline actions.
"""

import sys
import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

# Add src to path for logging
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from logging_config import get_logger

logger = get_logger(__name__)

from ..services import pipeline

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / "output"


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


class TaskStatus(BaseModel):
    status: str  # running | completed | error
    message: str | None = None
    result: dict[str, Any] | None = None


# In-memory task tracking (simple approach, could use Redis/DB for production)
_tasks: dict[str, TaskStatus] = {}


def get_run_dir(run_id: str) -> Path:
    run_dir = OUTPUT_DIR / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return run_dir


# Endpoints

@router.post("/create-seed", response_model=CreateSeedResponse)
async def create_seed(request: CreateSeedRequest):
    """Create a new seed and run directory."""
    if not request.news_text.strip():
        raise HTTPException(status_code=400, detail="News text cannot be empty")

    seed_path, run_dir = pipeline.create_seed(request.news_text)

    return CreateSeedResponse(
        run_id=run_dir.name,
        seed_path=str(seed_path)
    )


@router.get("/{run_id}/state", response_model=WorkflowState)
async def get_workflow_state(run_id: str):
    """Get current workflow state for a run."""
    run_dir = get_run_dir(run_id)
    state = pipeline.get_workflow_state(run_dir)
    return WorkflowState(**state)


@router.post("/{run_id}/generate-dialogue")
async def generate_dialogue(run_id: str, background_tasks: BackgroundTasks):
    """Start dialogue generation (runs in background)."""
    run_dir = get_run_dir(run_id)

    task_id = f"{run_id}:dialogue"
    if task_id in _tasks and _tasks[task_id].status == "running":
        raise HTTPException(status_code=409, detail="Task already running")

    _tasks[task_id] = TaskStatus(status="running", message="Generating dialogue...")

    def run_task():
        try:
            result = pipeline.generate_dialogue(run_dir)
            _tasks[task_id] = TaskStatus(
                status="completed",
                message="Dialogue generated successfully",
                result={"dialogue": result}
            )
        except Exception as e:
            _tasks[task_id] = TaskStatus(
                status="error",
                message=str(e)
            )

    background_tasks.add_task(run_task)

    return {"task_id": task_id, "status": "started"}


@router.put("/{run_id}/dialogue")
async def update_dialogue(run_id: str, request: DialogueUpdateRequest):
    """Update dialogue JSON for a run."""
    run_dir = get_run_dir(run_id)

    state = pipeline.get_workflow_state(run_dir)
    if not state["can_edit_dialogue"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot edit dialogue at this stage"
        )

    result = pipeline.update_dialogue(run_dir, request.dialogue)
    return {"status": "updated", "dialogue": result}


@router.post("/{run_id}/generate-audio")
async def generate_audio(run_id: str, background_tasks: BackgroundTasks):
    """Start audio generation (runs in background)."""
    run_dir = get_run_dir(run_id)

    state = pipeline.get_workflow_state(run_dir)
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
            pipeline.generate_audio(run_dir)

            # Also generate images after audio
            _tasks[task_id] = TaskStatus(
                status="running",
                message="Generating images..."
            )
            pipeline.generate_images(run_dir)

            # Generate YT metadata
            _tasks[task_id] = TaskStatus(
                status="running",
                message="Generating YouTube metadata..."
            )
            pipeline.generate_yt_metadata(run_dir)

            _tasks[task_id] = TaskStatus(
                status="completed",
                message="Audio, images, and metadata generated successfully"
            )
        except Exception as e:
            _tasks[task_id] = TaskStatus(
                status="error",
                message=str(e)
            )

    background_tasks.add_task(run_task)

    return {"task_id": task_id, "status": "started"}


@router.post("/{run_id}/generate-video")
async def generate_video(run_id: str, background_tasks: BackgroundTasks):
    """Start video generation (runs in background)."""
    run_dir = get_run_dir(run_id)

    state = pipeline.get_workflow_state(run_dir)
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
            video_path = pipeline.generate_video(run_dir)
            _tasks[task_id] = TaskStatus(
                status="completed",
                message="Video rendered successfully",
                result={"video_path": str(video_path)}
            )
        except Exception as e:
            _tasks[task_id] = TaskStatus(
                status="error",
                message=str(e)
            )

    background_tasks.add_task(run_task)

    return {"task_id": task_id, "status": "started"}


@router.post("/{run_id}/upload-youtube")
async def upload_youtube(run_id: str, background_tasks: BackgroundTasks):
    """Upload video to YouTube (runs in background)."""
    run_dir = get_run_dir(run_id)

    state = pipeline.get_workflow_state(run_dir)
    if not state["can_upload"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot upload at this stage"
        )

    task_id = f"{run_id}:youtube"
    if task_id in _tasks and _tasks[task_id].status == "running":
        raise HTTPException(status_code=409, detail="Task already running")

    _tasks[task_id] = TaskStatus(status="running", message="Uploading to YouTube...")

    def run_task():
        try:
            result = pipeline.upload_to_youtube(run_dir)
            _tasks[task_id] = TaskStatus(
                status="completed",
                message="Uploaded to YouTube successfully",
                result=result
            )
        except Exception as e:
            _tasks[task_id] = TaskStatus(
                status="error",
                message=str(e)
            )

    background_tasks.add_task(run_task)

    return {"task_id": task_id, "status": "started"}


@router.get("/task/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Get status of a background task."""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    return _tasks[task_id]


@router.put("/{run_id}/images")
async def update_images(run_id: str, request: ImagesUpdateRequest):
    """Update images.json for a run."""
    run_dir = get_run_dir(run_id)

    result = pipeline.update_images_metadata(run_dir, request.images)
    return {"status": "updated", "images": result}


@router.post("/{run_id}/regenerate-image/{image_id}")
async def regenerate_image(run_id: str, image_id: str, background_tasks: BackgroundTasks):
    """Regenerate a single image by ID."""
    run_dir = get_run_dir(run_id)

    task_id = f"{run_id}:image:{image_id}"
    if task_id in _tasks and _tasks[task_id].status == "running":
        raise HTTPException(status_code=409, detail="Task already running")

    _tasks[task_id] = TaskStatus(status="running", message=f"Regenerating {image_id}...")

    def run_task():
        try:
            result = pipeline.regenerate_single_image(run_dir, image_id)
            _tasks[task_id] = TaskStatus(
                status="completed",
                message=f"Image {image_id} regenerated successfully",
                result=result
            )
        except Exception as e:
            _tasks[task_id] = TaskStatus(
                status="error",
                message=str(e)
            )

    background_tasks.add_task(run_task)

    return {"task_id": task_id, "status": "started"}
