"""
Settings routes - API endpoints for global settings.
"""

import json
import secrets
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from ..config.tenant_registry import get_tenant
from ..services import settings as settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# OAuth state storage (in-memory, simple approach)
_oauth_states: dict[str, bool] = {}

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


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
    tenant = get_tenant("pl")
    token_path = PROJECT_ROOT / tenant.credentials_dir / "token.json"
    if not token_path.exists():
        raise HTTPException(status_code=404, detail="YouTube token not found")

    token_data = json.loads(token_path.read_text())
    return JSONResponse(content=token_data)


@router.post("/youtube-token/refresh")
async def start_youtube_oauth(request: Request):
    """Start YouTube OAuth flow. Returns authorization URL."""
    tenant = get_tenant("pl")
    client_secrets_path = PROJECT_ROOT / tenant.credentials_dir / "client_secrets.json"
    if not client_secrets_path.exists():
        raise HTTPException(status_code=404, detail="Client secrets not found")

    from google_auth_oauthlib.flow import Flow

    # Determine redirect URI based on request
    host = request.headers.get("host", "localhost:8000")
    scheme = request.headers.get("x-forwarded-proto", "http")
    redirect_uri = f"{scheme}://{host}/api/settings/youtube-token/callback"

    # Create flow
    flow = Flow.from_client_secrets_file(
        str(client_secrets_path),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

    # Generate state token
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = True

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )

    return {"auth_url": auth_url}


@router.get("/youtube-token/callback")
async def youtube_oauth_callback(code: str, state: str):
    """Handle OAuth callback from Google."""
    # Verify state
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid state")
    del _oauth_states[state]

    tenant = get_tenant("pl")
    client_secrets_path = PROJECT_ROOT / tenant.credentials_dir / "client_secrets.json"
    token_path = PROJECT_ROOT / tenant.credentials_dir / "token.json"

    if not client_secrets_path.exists():
        raise HTTPException(status_code=404, detail="Client secrets not found")

    from google_auth_oauthlib.flow import Flow

    # We need to reconstruct the flow - use a placeholder redirect_uri
    # The actual redirect already happened, we just need to exchange the code
    client_config = json.loads(client_secrets_path.read_text())

    # Get redirect_uri from client config
    if "web" in client_config:
        redirect_uri = client_config["web"].get("redirect_uris", [""])[0]
    else:
        # For installed app type, we need to use a custom redirect
        redirect_uri = "http://localhost:8000/api/settings/youtube-token/callback"

    flow = Flow.from_client_secrets_file(
        str(client_secrets_path),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

    # Exchange code for credentials
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Save token
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())

    # Redirect to settings page with success message
    return RedirectResponse(url="/?yt_token_refreshed=1")
