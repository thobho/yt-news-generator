"""
NewsData.io API client - fetches latest Polish news.
"""

import os
from datetime import date

import httpx

from ..core.logging_config import get_logger

logger = get_logger(__name__)

API_BASE = "https://newsdata.io/api/1/latest"

CATEGORIES = ["politics", "business", "world", "domestic"]


def _get_api_key() -> str:
    key = os.environ.get("NEWS_IO_API_KEY", "")
    if not key:
        raise RuntimeError("NEWS_IO_API_KEY env var is required")
    return key


async def fetch_news_from_newsdata() -> dict:
    """
    Fetch the latest Polish news from newsdata.io.

    Returns:
        Dict with title, publish_date, and items list matching the NewsSource schema.
    """
    api_key = _get_api_key()
    today = date.today().isoformat()

    items = []

    async with httpx.AsyncClient(timeout=20) as client:
        logger.info("Fetching NewsData.io news for Poland")
        response = await client.get(
            API_BASE,
            params={
                "apikey": api_key,
                "country": "pl",
                "language": "pl",
                "category": ",".join(CATEGORIES),
                "removeduplicate": 1,
                "size": 10,
            },
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "success":
            raise RuntimeError(f"NewsData.io API error: {data}")

        for article in data.get("results", []):
            # Free plan returns "ONLY AVAILABLE IN PAID PLANS" for content
            content = article.get("content") or ""
            if "ONLY AVAILABLE" in content:
                content = article.get("description") or ""

            title = article.get("title") or ""
            categories = article.get("category") or []
            category = categories[0] if categories else ""

            items.append({
                "id": article.get("article_id", ""),
                "title": title,
                "content": content,
                "category": category,
                "rating": 0,
                "total_votes": 0,
                "source": {
                    "name": article.get("source_name", ""),
                    "url": article.get("link", ""),
                },
                "_provider": "newsdata",
            })

    logger.info("Fetched %d items from NewsData.io", len(items))

    return {
        "title": f"NewsData.io Poland — {today}",
        "publish_date": today,
        "items": items,
    }
