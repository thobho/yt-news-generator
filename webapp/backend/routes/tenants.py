"""
Tenants route — list all configured tenants.
"""

from fastapi import APIRouter

from ..config.tenant_registry import load_tenants
from ..models import TenantInfo

router = APIRouter(tags=["tenants"])


@router.get("/tenants", response_model=list[TenantInfo])
async def list_tenants():
    """List all configured tenants."""
    return [TenantInfo(id=t.id, display_name=t.display_name) for t in load_tenants()]
