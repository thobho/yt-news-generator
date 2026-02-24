"""
Scheduler routes - API endpoints for per-tenant scheduler management.
"""

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional

from ..config.tenant_registry import TenantConfig
from ..dependencies import storage_dep
from ..services import scheduler as scheduler_service
from ..models import SchedulerConfig, SchedulerStatus, ScheduledRunConfig

router = APIRouter(tags=["scheduler"])


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
async def get_scheduler_status(tenant: TenantConfig = Depends(storage_dep)):
    """Get current scheduler status for this tenant."""
    return scheduler_service.get_tenant_scheduler_status(tenant)


@router.post("/enable", response_model=SchedulerConfig)
async def enable_scheduler(tenant: TenantConfig = Depends(storage_dep)):
    """Enable the scheduler for this tenant."""
    return scheduler_service.enable_tenant_scheduler(tenant)


@router.post("/disable", response_model=SchedulerConfig)
async def disable_scheduler(tenant: TenantConfig = Depends(storage_dep)):
    """Disable the scheduler for this tenant."""
    return scheduler_service.disable_tenant_scheduler(tenant)


@router.get("/config", response_model=SchedulerConfig)
async def get_config(tenant: TenantConfig = Depends(storage_dep)):
    """Get scheduler configuration for this tenant."""
    status = scheduler_service.get_tenant_scheduler_status(tenant)
    return status.config


@router.put("/config", response_model=SchedulerConfig)
async def update_config(updates: SchedulerConfigUpdate, tenant: TenantConfig = Depends(storage_dep)):
    """Update scheduler configuration for this tenant."""
    return scheduler_service.update_tenant_scheduler_config(tenant, updates.model_dump(exclude_none=True))


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_manual_run(background_tasks: BackgroundTasks, tenant: TenantConfig = Depends(storage_dep)):
    """
    Manually trigger a generation run for this tenant.
    The generation runs in the background.
    """
    async def run_generation():
        await scheduler_service.trigger_tenant_run(tenant)

    background_tasks.add_task(run_generation)

    return TriggerResponse(
        status="started",
        message=f"Manual generation started for tenant '{tenant.id}'"
    )


@router.post("/test-selection")
async def test_news_selection(tenant: TenantConfig = Depends(storage_dep)):
    """
    Test news selection without running generation for this tenant.
    Returns selected news items for preview.
    """
    return await scheduler_service.test_tenant_news_selection(tenant)
