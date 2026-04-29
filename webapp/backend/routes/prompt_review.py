"""
Prompt performance review routes.
"""

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config.tenant_registry import TenantConfig
from ..dependencies import storage_dep
from ..services import prompts as prompts_service

router = APIRouter(tags=["prompt-review"])


class PromptAnalysis(BaseModel):
    prompt_type: str
    current_prompt_id: str
    assessment: str
    suggested_changes: list[str]
    suggested_prompt: str


class PromptReviewReport(BaseModel):
    summary: str
    prompt_analyses: list[PromptAnalysis]
    topic_insights: str
    experiment_ideas: list[str]


class ApplySuggestionRequest(BaseModel):
    prompt_type: str  # analysis type: dialogue_step1, dialogue_step2, dialogue_step3, image, yt_metadata
    suggested_prompt: str


class ApplySuggestionResponse(BaseModel):
    prompt_id: str
    prompt_type: str


# Map analysis prompt_type to (PromptType, step)
_ANALYSIS_TYPE_MAP: dict[str, tuple[str, str]] = {
    "dialogue_step1": ("dialogue", "step1"),
    "dialogue_step2": ("dialogue", "step2"),
    "dialogue_step3": ("dialogue", "step3"),
    "image": ("image", "main"),
    "yt_metadata": ("yt-metadata", "main"),
}


def _generate_review_prompt_id(prompt_type: str) -> str:
    """Generate a unique prompt ID like 'review-2026-04-30'."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_id = f"review-{date_str}"

    existing = prompts_service.list_prompts(prompt_type)  # type: ignore[arg-type]
    existing_ids = {p.id for p in existing}

    if base_id not in existing_ids:
        return base_id

    # Append incrementing suffix
    for i in range(2, 100):
        candidate = f"{base_id}-{i}"
        if candidate not in existing_ids:
            return candidate

    return f"{base_id}-{datetime.now().strftime('%H%M%S')}"


@router.post("/generate", response_model=PromptReviewReport)
async def generate_review(_: TenantConfig = Depends(storage_dep)):
    """Generate a prompt performance review report using LLM analysis."""
    from ..services.prompt_review import generate_prompt_review

    result = await asyncio.to_thread(generate_prompt_review)
    return PromptReviewReport(**result)


@router.post("/apply", response_model=ApplySuggestionResponse)
async def apply_suggestion(request: ApplySuggestionRequest, _: TenantConfig = Depends(storage_dep)):
    """Create a new prompt version from a review suggestion and set it as active."""
    mapping = _ANALYSIS_TYPE_MAP.get(request.prompt_type)
    if not mapping:
        raise HTTPException(status_code=400, detail=f"Unknown analysis prompt type: {request.prompt_type}")

    real_type, step = mapping
    new_id = _generate_review_prompt_id(real_type)

    if step == "main":
        # Non-dialogue or dialogue step1 standalone — simple create
        await asyncio.to_thread(
            prompts_service.create_prompt,
            prompt_type=real_type,
            prompt_id=new_id,
            content=request.suggested_prompt,
            set_active=True,
        )
    else:
        # Dialogue step — copy current active prompt, replace only the target step
        active_id = prompts_service.get_active_prompt_id("dialogue")
        current = prompts_service.get_prompt("dialogue", active_id) if active_id else None

        content = current.content if current else ""
        step2 = current.step2_content if current else None
        step3 = current.step3_content if current else None
        temp = current.temperature if current else 0.7
        temp2 = current.step2_temperature if current else 0.5
        temp3 = current.step3_temperature if current else 0.6

        if step == "step1":
            content = request.suggested_prompt
        elif step == "step2":
            step2 = request.suggested_prompt
        elif step == "step3":
            step3 = request.suggested_prompt

        await asyncio.to_thread(
            prompts_service.create_prompt,
            prompt_type="dialogue",
            prompt_id=new_id,
            content=content,
            temperature=temp,
            step2_content=step2,
            step2_temperature=temp2,
            step3_content=step3,
            step3_temperature=temp3,
            set_active=True,
        )

    return ApplySuggestionResponse(prompt_id=new_id, prompt_type=real_type)
