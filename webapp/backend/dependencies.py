"""
Shared FastAPI dependencies for tenant-scoped requests.

Usage in routes (after task 06 adds /api/tenants/{tenant_id}/ prefix):

    from ..dependencies import tenant_dep, storage_dep
    from ..config.tenant_registry import TenantConfig

    @router.get("/runs")
    async def list_runs(tenant: TenantConfig = Depends(storage_dep)):
        ...  # storage_config._tenant_prefix is now set for this request
"""

from fastapi import Depends, Path

from .config.tenant_registry import TenantConfig, get_tenant


async def tenant_dep(tenant_id: str = Path(...)) -> TenantConfig:
    """Validate tenant_id from URL path and return its TenantConfig."""
    return get_tenant(tenant_id)


async def storage_dep(tenant: TenantConfig = Depends(tenant_dep)) -> TenantConfig:
    """
    Set the tenant storage prefix for this request context.

    All subsequent calls to get_data_storage(), get_output_storage(),
    get_run_storage() etc. within this request will use the correct tenant path.
    Returns the TenantConfig for additional use by route handlers.
    """
    import sys
    from pathlib import Path as P
    PROJECT_ROOT = P(__file__).parent.parent.parent
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

    from storage_config import set_tenant_prefix, set_credentials_dir
    set_tenant_prefix(tenant.storage_prefix)
    set_credentials_dir(tenant.credentials_dir)
    return tenant
