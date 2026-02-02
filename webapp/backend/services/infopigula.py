"""
InfoPigula API client - fetches daily news from infopigula.pl.
"""

import os
import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from logging_config import get_logger

logger = get_logger(__name__)

# JWT token cache
_token: Optional[str] = None
_token_expires_at: float = 0

API_BASE = "https://infopigula.pl/api/v1"

# Browser-like headers to avoid scraping detection
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://infopigula.pl/",
    "Origin": "https://infopigula.pl",
}

TOKEN_TTL = 3600  # 1 hour


def _get_credentials() -> tuple[str, str]:
    email = os.environ.get("INFOPIGULA_EMAIL", "")
    password = os.environ.get("INFOPIGULA_PASSWORD", "")
    if not email or not password:
        raise RuntimeError("INFOPIGULA_EMAIL and INFOPIGULA_PASSWORD env vars are required")
    return email, password


async def _authenticate() -> str:
    """Authenticate with InfoPigula API and return JWT token."""
    global _token, _token_expires_at

    # Return cached token if still valid
    if _token and time.time() < _token_expires_at:
        return _token

    email, password = _get_credentials()
    logger.info("Authenticating with InfoPigula API")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE}/login-user",
            json={"email": email, "password": password},
            headers=BROWSER_HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

    _token = data.get("token") or data.get("accessToken")
    if not _token:
        raise RuntimeError(f"No token in login response: {list(data.keys())}")

    _token_expires_at = time.time() + TOKEN_TTL
    logger.info("InfoPigula authentication successful")
    return _token


def _extract_title(html: str) -> Optional[str]:
    """Extract title from first <strong> tag in HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    strong = soup.find("strong")
    if strong:
        return strong.get_text(strip=True)
    return None


def _strip_html(html: str) -> str:
    """Strip HTML tags and return plain text."""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n", strip=True)


async def fetch_news() -> dict:
    """
    Fetch the latest news release.

    Returns:
        Dict with title, publish_date, and items list
    """
    token = await _authenticate()

    headers = {
        **BROWSER_HEADERS,
        "Authorization": f"Bearer {token}",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE}/user-dashboard/release",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

    items = []
    for category in data.get("categories", []):
        category_name = category.get("name", "")
        for news in category.get("news", []):
            raw_content = news.get("content", "")
            title = _extract_title(raw_content)
            content = _strip_html(raw_content)

            source = news.get("source") or {}
            items.append({
                "id": news.get("id"),
                "title": title,
                "content": content,
                "category": category_name,
                "rating": news.get("rating", 0),
                "total_votes": news.get("totalVotes", 0),
                "source": {
                    "name": source.get("name", ""),
                    "url": source.get("url", ""),
                },
            })

    return {
        "title": data.get("title", ""),
        "publish_date": data.get("publishDate", ""),
        "items": items,
    }
