"""
Settings routes - API endpoints for global settings.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..services import settings as settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])

# YouTube token path (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
YT_TOKEN_PATH = PROJECT_ROOT / "credentials" / "token.json"


class SettingsResponse(BaseModel):
    prompt_version: str
    tts_engine: str
    image_engine: str
    fal_model: str


class SettingsUpdateRequest(BaseModel):
    prompt_version: Optional[str] = None
    tts_engine: Optional[str] = None
    image_engine: Optional[str] = None
    fal_model: Optional[str] = None


class PromptVersionInfo(BaseModel):
    version: str
    label: str
    files: dict[str, str]


class TTSEngineInfo(BaseModel):
    id: str
    label: str
    description: str


class ImageEngineInfo(BaseModel):
    id: str
    label: str
    description: str


class FalModelInfo(BaseModel):
    id: str
    label: str
    description: str


class AvailableSettingsResponse(BaseModel):
    prompt_versions: list[PromptVersionInfo]
    tts_engines: list[TTSEngineInfo]
    image_engines: list[ImageEngineInfo]
    fal_models: list[FalModelInfo]


@router.get("", response_model=SettingsResponse)
async def get_settings():
    """Get current settings."""
    current = settings_service.load_settings()
    return SettingsResponse(
        prompt_version=current.prompt_version,
        tts_engine=current.tts_engine,
        image_engine=current.image_engine,
        fal_model=current.fal_model,
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(request: SettingsUpdateRequest):
    """Update settings."""
    current = settings_service.load_settings()

    if request.prompt_version is not None:
        available = [v["version"] for v in settings_service.get_available_prompt_versions()]
        if request.prompt_version not in available:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prompt version. Available: {available}"
            )
        current.prompt_version = request.prompt_version  # type: ignore

    if request.tts_engine is not None:
        valid_engines = [e["id"] for e in settings_service.get_available_tts_engines()]
        if request.tts_engine not in valid_engines:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Invalid TTS engine. Available: {valid_engines}"
            )
        current.tts_engine = request.tts_engine  # type: ignore

    if request.image_engine is not None:
        valid_engines = [e["id"] for e in settings_service.get_available_image_engines()]
        if request.image_engine not in valid_engines:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image engine. Available: {valid_engines}"
            )
        current.image_engine = request.image_engine  # type: ignore

    if request.fal_model is not None:
        valid_models = [m["id"] for m in settings_service.get_available_fal_models()]
        if request.fal_model not in valid_models:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"Invalid fal model. Available: {valid_models}"
            )
        current.fal_model = request.fal_model

    settings_service.save_settings(current)

    return SettingsResponse(
        prompt_version=current.prompt_version,
        tts_engine=current.tts_engine,
        image_engine=current.image_engine,
        fal_model=current.fal_model,
    )


@router.get("/available", response_model=AvailableSettingsResponse)
async def get_available_settings():
    """Get available setting options."""
    versions = settings_service.get_available_prompt_versions()
    tts_engines = settings_service.get_available_tts_engines()
    image_engines = settings_service.get_available_image_engines()
    fal_models = settings_service.get_available_fal_models()
    return AvailableSettingsResponse(
        prompt_versions=[PromptVersionInfo(**v) for v in versions],
        tts_engines=[TTSEngineInfo(**e) for e in tts_engines],
        image_engines=[ImageEngineInfo(**e) for e in image_engines],
        fal_models=[FalModelInfo(**m) for m in fal_models],
    )


@router.get("/youtube-token")
async def get_youtube_token():
    """Get YouTube OAuth token for updating GitHub secrets."""
    if not YT_TOKEN_PATH.exists():
        raise HTTPException(status_code=404, detail="YouTube token not found")

    import json
    token_data = json.loads(YT_TOKEN_PATH.read_text())
    return JSONResponse(content=token_data)
