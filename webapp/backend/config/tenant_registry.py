import json
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel

TENANTS_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "tenants.json"


class TenantConfig(BaseModel):
    id: str
    display_name: str
    language: str
    news_source: str
    storage_prefix: str
    credentials_dir: str


@lru_cache
def load_tenants() -> tuple[TenantConfig, ...]:
    raw = json.loads(TENANTS_CONFIG_PATH.read_text())
    return tuple(TenantConfig(**t) for t in raw)


def get_tenant(tenant_id: str) -> TenantConfig:
    for t in load_tenants():
        if t.id == tenant_id:
            return t
    raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
