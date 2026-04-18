"""
Prompt performance review routes.
"""

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config.tenant_registry import TenantConfig
from ..dependencies import storage_dep

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


@router.post("/generate", response_model=PromptReviewReport)
async def generate_review(_: TenantConfig = Depends(storage_dep)):
    """Generate a prompt performance review report using LLM analysis."""
    from ..services.prompt_review import generate_prompt_review

    result = await asyncio.to_thread(generate_prompt_review)
    return PromptReviewReport(**result)
