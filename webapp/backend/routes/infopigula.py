"""
News routes — fetch today's news for a tenant via its configured NewsSource.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config.tenant_registry import TenantConfig
from ..dependencies import tenant_dep
from ..services.news_source import get_news_source

router = APIRouter(tags=["infopigula"])


class NewsSourceModel(BaseModel):
    name: str
    url: str


class NewsItem(BaseModel):
    id: str
    title: Optional[str]
    content: str
    category: str
    rating: float
    total_votes: int
    source: NewsSourceModel


class NewsResponse(BaseModel):
    title: str
    publish_date: str
    items: list[NewsItem]


@router.get("/news", response_model=NewsResponse)
async def get_news(tenant: TenantConfig = Depends(tenant_dep)):
    """Fetch the latest news release for the tenant."""
    source = get_news_source(tenant)
    try:
        data = await source.fetch_news()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch news: {e}")

    return NewsResponse(
        title=data["title"],
        publish_date=data["publish_date"],
        items=[NewsItem(**item) for item in data["items"]],
    )
