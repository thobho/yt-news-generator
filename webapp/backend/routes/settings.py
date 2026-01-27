"""
Settings routes - API endpoints for global settings.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import settings as settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    prompt_version: str


class SettingsUpdateRequest(BaseModel):
    prompt_version: str


class PromptVersionInfo(BaseModel):
    version: str
    label: str
    files: dict[str, str]


class AvailableSettingsResponse(BaseModel):
    prompt_versions: list[PromptVersionInfo]


@router.get("", response_model=SettingsResponse)
async def get_settings():
    """Get current settings."""
    current = settings_service.load_settings()
    return SettingsResponse(prompt_version=current.prompt_version)


@router.put("", response_model=SettingsResponse)
async def update_settings(request: SettingsUpdateRequest):
    """Update settings."""
    # Validate prompt version
    available = [v["version"] for v in settings_service.get_available_prompt_versions()]
    if request.prompt_version not in available:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"Invalid prompt version. Available: {available}"
        )

    current = settings_service.load_settings()
    current.prompt_version = request.prompt_version  # type: ignore
    settings_service.save_settings(current)

    return SettingsResponse(prompt_version=current.prompt_version)


@router.get("/available", response_model=AvailableSettingsResponse)
async def get_available_settings():
    """Get available setting options."""
    versions = settings_service.get_available_prompt_versions()
    return AvailableSettingsResponse(
        prompt_versions=[PromptVersionInfo(**v) for v in versions]
    )
