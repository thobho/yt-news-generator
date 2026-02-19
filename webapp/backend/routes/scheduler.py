"""
Scheduler routes - API endpoints for scheduler management.
"""

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from ..services import scheduler as scheduler_service
from ..models import SchedulerConfig, SchedulerStatus, ScheduledRunConfig

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


class SchedulerConfigUpdate(BaseModel):
    """Request body for config updates."""
    enabled: Optional[bool] = None
    generation_time: Optional[str] = None
    publish_time: Optional[str] = None
    runs: Optional[list[ScheduledRunConfig]] = None  # Per-run configurations


class TriggerResponse(BaseModel):
    """Response for manual trigger."""
    status: str
    message: str


@router.get("/status", response_model=SchedulerStatus)
async def get_scheduler_status():
    """Get current scheduler status."""
    return scheduler_service.get_scheduler_status()


@router.post("/enable", response_model=SchedulerConfig)
async def enable_scheduler():
    """Enable the scheduler."""
    return scheduler_service.enable_scheduler()


@router.post("/disable", response_model=SchedulerConfig)
async def disable_scheduler():
    """Disable the scheduler."""
    return scheduler_service.disable_scheduler()


@router.get("/config", response_model=SchedulerConfig)
async def get_config():
    """Get scheduler configuration."""
    status = scheduler_service.get_scheduler_status()
    return status.config


@router.put("/config", response_model=SchedulerConfig)
async def update_config(updates: SchedulerConfigUpdate):
    """Update scheduler configuration."""
    return scheduler_service.update_scheduler_config(updates.model_dump(exclude_none=True))


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_manual_run(background_tasks: BackgroundTasks):
    """
    Manually trigger a generation run.
    The generation runs in the background.
    """
    async def run_generation():
        await scheduler_service.trigger_manual_run()

    background_tasks.add_task(run_generation)

    return TriggerResponse(
        status="started",
        message="Manual generation started in background"
    )


@router.post("/test-selection")
async def test_news_selection():
    """
    Test news selection without running generation.
    Returns selected news items for preview.
    """
    return await scheduler_service.test_news_selection()
