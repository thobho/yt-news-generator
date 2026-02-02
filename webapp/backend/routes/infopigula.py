"""
InfoPigula routes - API endpoints for fetching news from infopigula.pl.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import infopigula

router = APIRouter(prefix="/api/infopigula", tags=["infopigula"])


class NewsSource(BaseModel):
    name: str
    url: str


class NewsItem(BaseModel):
    id: str
    title: Optional[str]
    content: str
    category: str
    rating: float
    total_votes: int
    source: NewsSource


class NewsResponse(BaseModel):
    title: str
    publish_date: str
    items: list[NewsItem]


@router.get("/news", response_model=NewsResponse)
async def get_news():
    """Fetch the latest news release from InfoPigula."""
    try:
        data = await infopigula.fetch_news()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch news: {e}")

    return NewsResponse(
        title=data["title"],
        publish_date=data["publish_date"],
        items=[NewsItem(**item) for item in data["items"]],
    )
