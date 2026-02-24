"""
NewsAPI.org client - fetches top US headlines grouped by category.
"""

import os
from datetime import date

import httpx

from ..core.logging_config import get_logger

logger = get_logger(__name__)

API_BASE = "https://newsapi.org/v2"

CATEGORIES = ["general", "business", "technology", "entertainment", "sports", "science", "health"]

PAGE_SIZE = 10  # articles per category


def _get_api_key() -> str:
    key = os.environ.get("NEWSAPI_TOKEN", "")
    if not key:
        raise RuntimeError("NEWSAPI_TOKEN env var is required")
    return key


async def fetch_news_from_newsapi() -> dict:
    """
    Fetch today's top US headlines from NewsAPI.org, grouped by category.

    Returns:
        Dict with title, publish_date, and items list matching the NewsSource schema.
    """
    api_key = _get_api_key()
    today = date.today().isoformat()

    items = []

    async with httpx.AsyncClient(timeout=15) as client:
        for category in CATEGORIES:
            logger.info("Fetching NewsAPI category: %s", category)
            response = await client.get(
                f"{API_BASE}/top-headlines",
                params={
                    "country": "us",
                    "category": category,
                    "pageSize": PAGE_SIZE,
                    "apiKey": api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            for article in data.get("articles", []):
                source = article.get("source") or {}
                title = article.get("title") or ""
                # Strip " - Source Name" suffix that NewsAPI appends to titles
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0]

                content = article.get("content") or article.get("description") or ""
                # NewsAPI truncates content with "[+N chars]" — strip that suffix
                if content and "[+" in content:
                    content = content.split("[+")[0].strip()

                items.append({
                    "id": article.get("url", ""),
                    "title": title,
                    "content": content,
                    "category": category,
                    "rating": 0,
                    "total_votes": 0,
                    "source": {
                        "name": source.get("name", ""),
                        "url": article.get("url", ""),
                    },
                })

    return {
        "title": f"US Top Headlines — {today}",
        "publish_date": today,
        "items": items,
    }
