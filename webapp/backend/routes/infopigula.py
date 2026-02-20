"""
News routes — fetch today's news for a tenant via its configured NewsSource.

URL is still /api/infopigula/news until Task 06 renames it to
/api/tenants/{tenant_id}/news and wires in the tenant path parameter.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config.tenant_registry import get_tenant
from ..services.news_source import get_news_source

router = APIRouter(prefix="/api/infopigula", tags=["infopigula"])


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
async def get_news():
    """Fetch the latest news release for the pl tenant (default until Task 06)."""
    tenant = get_tenant("pl")
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
