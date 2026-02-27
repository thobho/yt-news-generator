"""
Settings routes - API endpoints for global settings.
"""

import json
import secrets
import tempfile
import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from ..config.tenant_registry import TenantConfig
from ..core.storage_config import get_data_storage
from ..dependencies import storage_dep, tenant_dep
from ..services import settings as settings_service
from ..services.settings import Speaker

router = APIRouter(tags=["settings"])

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
async def get_settings(_: TenantConfig = Depends(storage_dep)):
    """Get current settings."""
    current = settings_service.load_settings()
    return SettingsResponse(
        prompt_version=current.prompt_version,
        tts_engine=current.tts_engine,
        image_engine=current.image_engine,
        fal_model=current.fal_model,
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(request: SettingsUpdateRequest, _: TenantConfig = Depends(storage_dep)):
    """Update settings."""
    current = settings_service.load_settings()

    if request.prompt_version is not None:
        available = [v["version"] for v in settings_service.get_available_prompt_versions()]
        if request.prompt_version not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prompt version. Available: {available}"
            )
        current.prompt_version = request.prompt_version  # type: ignore

    if request.tts_engine is not None:
        valid_engines = [e["id"] for e in settings_service.get_available_tts_engines()]
        if request.tts_engine not in valid_engines:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid TTS engine. Available: {valid_engines}"
            )
        current.tts_engine = request.tts_engine  # type: ignore

    if request.image_engine is not None:
        valid_engines = [e["id"] for e in settings_service.get_available_image_engines()]
        if request.image_engine not in valid_engines:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image engine. Available: {valid_engines}"
            )
        current.image_engine = request.image_engine  # type: ignore

    if request.fal_model is not None:
        valid_models = [m["id"] for m in settings_service.get_available_fal_models()]
        if request.fal_model not in valid_models:
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
async def get_available_settings(_: TenantConfig = Depends(storage_dep)):
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


class SpeakerResponse(BaseModel):
    name: str
    storage_key: str


class MoveSpeakerRequest(BaseModel):
    direction: Literal["up", "down"]


@router.get("/speakers", response_model=list[SpeakerResponse])
async def get_speakers(_: TenantConfig = Depends(storage_dep)):
    """Get ordered list of speakers."""
    current = settings_service.load_settings()
    return [SpeakerResponse(name=s.name, storage_key=s.storage_key) for s in current.speakers]


@router.post("/speakers", response_model=list[SpeakerResponse])
async def upload_speaker(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    _: TenantConfig = Depends(storage_dep),
):
    """Upload a voice sample and add it to the speakers list."""
    # Validate extension
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in (".wav", ".mp3"):
        raise HTTPException(status_code=400, detail="Only .wav and .mp3 files are allowed")

    # Default name to filename stem
    speaker_name = name or Path(filename).stem or "Speaker"

    # Save uploaded file to a temp location
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_in:
        tmp_in.write(await file.read())
        tmp_in_path = Path(tmp_in.name)

    # Normalize with ffmpeg: 24kHz, mono, max 30s
    tmp_out_path = tmp_in_path.parent / (tmp_in_path.stem + "_norm.wav")
    try:
        import subprocess
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(tmp_in_path),
                "-ar", "24000",
                "-ac", "1",
                "-t", "30",
                str(tmp_out_path),
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"ffmpeg normalization failed: {result.stderr.decode()[:200]}"
            )

        # Generate storage key and upload
        storage_key = f"voices/{uuid.uuid4().hex[:8]}.wav"
        data_storage = get_data_storage()
        data_storage.write_bytes(storage_key, tmp_out_path.read_bytes())

    finally:
        tmp_in_path.unlink(missing_ok=True)
        tmp_out_path.unlink(missing_ok=True)

    # Append to speakers list and save
    current = settings_service.load_settings()
    current.speakers.append(Speaker(name=speaker_name, storage_key=storage_key))
    settings_service.save_settings(current)

    return [SpeakerResponse(name=s.name, storage_key=s.storage_key) for s in current.speakers]


@router.delete("/speakers/{index}", response_model=list[SpeakerResponse])
async def delete_speaker(index: int, _: TenantConfig = Depends(storage_dep)):
    """Remove a speaker by index and delete its voice file."""
    current = settings_service.load_settings()
    if index < 0 or index >= len(current.speakers):
        raise HTTPException(status_code=404, detail="Speaker index out of range")

    speaker = current.speakers[index]

    # Delete voice file from storage
    try:
        data_storage = get_data_storage()
        if data_storage.exists(speaker.storage_key):
            data_storage.delete(speaker.storage_key)
    except Exception:
        pass  # Don't fail if file is already gone

    current.speakers.pop(index)
    settings_service.save_settings(current)

    return [SpeakerResponse(name=s.name, storage_key=s.storage_key) for s in current.speakers]


@router.put("/speakers/{index}/move", response_model=list[SpeakerResponse])
async def move_speaker(index: int, request: MoveSpeakerRequest, _: TenantConfig = Depends(storage_dep)):
    """Reorder a speaker up or down in the list."""
    current = settings_service.load_settings()
    if index < 0 or index >= len(current.speakers):
        raise HTTPException(status_code=404, detail="Speaker index out of range")

    if request.direction == "up":
        if index == 0:
            raise HTTPException(status_code=400, detail="Speaker is already first")
        current.speakers[index - 1], current.speakers[index] = (
            current.speakers[index], current.speakers[index - 1]
        )
    else:
        if index >= len(current.speakers) - 1:
            raise HTTPException(status_code=400, detail="Speaker is already last")
        current.speakers[index], current.speakers[index + 1] = (
            current.speakers[index + 1], current.speakers[index]
        )

    settings_service.save_settings(current)

    return [SpeakerResponse(name=s.name, storage_key=s.storage_key) for s in current.speakers]


@router.get("/youtube-token")
async def get_youtube_token(tenant: TenantConfig = Depends(tenant_dep)):
    """Get YouTube OAuth token for updating GitHub secrets."""
    token_path = PROJECT_ROOT / tenant.credentials_dir / "token.json"
    if not token_path.exists():
        raise HTTPException(status_code=404, detail="YouTube token not found")

    token_data = json.loads(token_path.read_text())
    return JSONResponse(content=token_data)


@router.post("/youtube-token/refresh")
async def start_youtube_oauth(request: Request, tenant: TenantConfig = Depends(tenant_dep)):
    """Start YouTube OAuth flow. Returns authorization URL."""
    client_secrets_path = PROJECT_ROOT / tenant.credentials_dir / "client_secrets.json"
    if not client_secrets_path.exists():
        raise HTTPException(status_code=404, detail="Client secrets not found")

    from google_auth_oauthlib.flow import Flow

    # Determine redirect URI based on request
    host = request.headers.get("host", "localhost:8000")
    scheme = request.headers.get("x-forwarded-proto", "http")
    redirect_uri = f"{scheme}://{host}/api/tenants/{tenant.id}/settings/youtube-token/callback"

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
async def youtube_oauth_callback(code: str, state: str, tenant: TenantConfig = Depends(tenant_dep)):
    """Handle OAuth callback from Google."""
    # Verify state
    if state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid state")
    del _oauth_states[state]

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
        redirect_uri = f"http://localhost:8000/api/tenants/{tenant.id}/settings/youtube-token/callback"

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
