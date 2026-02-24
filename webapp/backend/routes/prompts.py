"""
Prompts routes - API endpoints for managing prompt templates.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config.tenant_registry import TenantConfig
from ..dependencies import storage_dep
from ..services import prompts as prompts_service
from ..services.prompts import PromptType, PROMPT_TYPES, PromptInfo, PromptContent

router = APIRouter(tags=["prompts"])


class PromptListResponse(BaseModel):
    prompt_type: PromptType
    prompts: list[PromptInfo]
    active_id: str | None


class AllPromptsResponse(BaseModel):
    types: list[dict]


class CreatePromptRequest(BaseModel):
    prompt_id: str
    content: str
    temperature: float | None = None
    step2_content: str | None = None
    step2_temperature: float | None = None
    step3_content: str | None = None
    step3_temperature: float | None = None
    set_active: bool = False


class UpdatePromptRequest(BaseModel):
    content: str
    temperature: float | None = None
    step2_content: str | None = None
    step2_temperature: float | None = None
    step3_content: str | None = None
    step3_temperature: float | None = None


class SetActiveRequest(BaseModel):
    prompt_id: str


class MigrateResponse(BaseModel):
    migrated: dict[str, list[str]]


@router.get("", response_model=AllPromptsResponse)
async def list_all_prompts(_: TenantConfig = Depends(storage_dep)):
    """List all prompt types with their prompts."""
    types = []
    for prompt_type in PROMPT_TYPES:
        prompts = prompts_service.list_prompts(prompt_type)
        active_id = prompts_service.get_active_prompt_id(prompt_type)
        types.append({
            "type": prompt_type,
            "label": _get_type_label(prompt_type),
            "description": _get_type_description(prompt_type),
            "prompts": [p.model_dump() for p in prompts],
            "active_id": active_id,
            "has_step2": prompt_type == "dialogue"
        })
    return AllPromptsResponse(types=types)


@router.get("/{prompt_type}", response_model=PromptListResponse)
async def list_prompts(prompt_type: PromptType, _: TenantConfig = Depends(storage_dep)):
    """List all prompts of a given type."""
    prompts = prompts_service.list_prompts(prompt_type)
    active_id = prompts_service.get_active_prompt_id(prompt_type)
    return PromptListResponse(
        prompt_type=prompt_type,
        prompts=prompts,
        active_id=active_id
    )


@router.get("/{prompt_type}/{prompt_id}")
async def get_prompt(prompt_type: PromptType, prompt_id: str, _: TenantConfig = Depends(storage_dep)):
    """Get full prompt content."""
    prompt = prompts_service.get_prompt(prompt_type, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt.model_dump()


@router.post("/{prompt_type}")
async def create_prompt(prompt_type: PromptType, request: CreatePromptRequest, _: TenantConfig = Depends(storage_dep)):
    """Create a new prompt."""
    try:
        prompt = prompts_service.create_prompt(
            prompt_type=prompt_type,
            prompt_id=request.prompt_id,
            content=request.content,
            temperature=request.temperature,
            step2_content=request.step2_content,
            step2_temperature=request.step2_temperature,
            step3_content=request.step3_content,
            step3_temperature=request.step3_temperature,
            set_active=request.set_active
        )
        return prompt.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{prompt_type}/{prompt_id}")
async def update_prompt(prompt_type: PromptType, prompt_id: str, request: UpdatePromptRequest, _: TenantConfig = Depends(storage_dep)):
    """Update an existing prompt."""
    try:
        prompt = prompts_service.update_prompt(
            prompt_type=prompt_type,
            prompt_id=prompt_id,
            content=request.content,
            temperature=request.temperature,
            step2_content=request.step2_content,
            step2_temperature=request.step2_temperature,
            step3_content=request.step3_content,
            step3_temperature=request.step3_temperature
        )
        return prompt.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{prompt_type}/{prompt_id}")
async def delete_prompt(prompt_type: PromptType, prompt_id: str, _: TenantConfig = Depends(storage_dep)):
    """Delete a prompt."""
    try:
        success = prompts_service.delete_prompt(prompt_type, prompt_id)
        if not success:
            raise HTTPException(status_code=404, detail="Prompt not found")
        return {"status": "deleted", "prompt_id": prompt_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{prompt_type}/active")
async def set_active_prompt(prompt_type: PromptType, request: SetActiveRequest, _: TenantConfig = Depends(storage_dep)):
    """Set the active prompt for a type."""
    try:
        prompts_service.set_active_prompt(prompt_type, request.prompt_id)
        return {"status": "ok", "active_id": request.prompt_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/migrate")
async def migrate_prompts(_: TenantConfig = Depends(storage_dep)):
    """Migrate old prompts to new structure."""
    migrated = prompts_service.migrate_old_prompts()
    return MigrateResponse(migrated=migrated)


def _get_type_label(prompt_type: PromptType) -> str:
    """Get display label for prompt type."""
    labels = {
        "dialogue": "Dialogue Prompts",
        "image": "Image Generation Prompts",
        "research": "Research/Summarizer Prompts",
        "yt-metadata": "YouTube Metadata Prompts"
    }
    return labels.get(prompt_type, prompt_type)


def _get_type_description(prompt_type: PromptType) -> str:
    """Get description for prompt type."""
    descriptions = {
        "dialogue": "Prompts for generating dialogue scripts. 3-step system: main (structure), step-2 (logic fix), step-3 (language polish).",
        "image": "Prompts for AI image generation (DALL-E style).",
        "research": "Prompts for summarizing news articles from Perplexity research.",
        "yt-metadata": "Prompts for generating YouTube video titles, descriptions, and tags."
    }
    return descriptions.get(prompt_type, "")
