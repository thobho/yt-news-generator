"""
News selection prompt review routes.
"""

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config.tenant_registry import TenantConfig
from ..dependencies import storage_dep
from ..services import prompts as prompts_service

router = APIRouter(tags=["news-selection-review"])


class TopicPerformance(BaseModel):
    category: str
    run_count: int
    avg_score: float
    avg_views: float
    avg_retention: float
    insight: str


class NewsSelectionReviewReport(BaseModel):
    summary: str
    topic_performance: list[TopicPerformance]
    current_prompt_assessment: str
    suggested_changes: list[str]
    suggested_prompt: str
    experiment_ideas: list[str]


class ApplyNewsSelectionRequest(BaseModel):
    suggested_prompt: str


class ApplyNewsSelectionResponse(BaseModel):
    prompt_id: str
    prompt_type: str


def _generate_review_prompt_id() -> str:
    """Generate a unique prompt ID like 'review-2026-04-30'."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_id = f"review-{date_str}"

    existing = prompts_service.list_prompts("news-selection")
    existing_ids = {p.id for p in existing}

    if base_id not in existing_ids:
        return base_id

    for i in range(2, 100):
        candidate = f"{base_id}-{i}"
        if candidate not in existing_ids:
            return candidate

    return f"{base_id}-{datetime.now().strftime('%H%M%S')}"


@router.post("/generate", response_model=NewsSelectionReviewReport)
async def generate_review(_: TenantConfig = Depends(storage_dep)):
    """Generate a news selection prompt review report using LLM analysis."""
    from ..services.news_selection_review import generate_news_selection_review

    result = await asyncio.to_thread(generate_news_selection_review)
    return NewsSelectionReviewReport(**result)


@router.post("/apply", response_model=ApplyNewsSelectionResponse)
async def apply_suggestion(
    request: ApplyNewsSelectionRequest,
    _: TenantConfig = Depends(storage_dep),
):
    """Create a new news-selection prompt from a review suggestion and set it as active."""
    new_id = _generate_review_prompt_id()

    await asyncio.to_thread(
        prompts_service.create_prompt,
        prompt_type="news-selection",
        prompt_id=new_id,
        content=request.suggested_prompt,
        set_active=True,
    )

    return ApplyNewsSelectionResponse(prompt_id=new_id, prompt_type="news-selection")
