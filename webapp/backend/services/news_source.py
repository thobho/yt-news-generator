"""
News source abstraction — each tenant can have its own news provider.

Add new sources by:
1. Implementing a subclass of NewsSource
2. Registering it in _SOURCES and config/tenants.json

Multiple sources can be combined with "+" in the tenant config, e.g. "infopigula+newsdata".
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import date

from ..config.tenant_registry import TenantConfig

logger = logging.getLogger(__name__)


class NewsSource(ABC):
    @abstractmethod
    async def fetch_news(self) -> dict:
        """
        Fetch today's news items for this tenant.

        Returns a dict with keys: title, publish_date, items[].
        Each item has: id, title, content, category, rating, total_votes, source{name, url}.
        """
        ...


class InfoPigulaNewsSource(NewsSource):
    """Polish news from infopigula.pl."""

    async def fetch_news(self) -> dict:
        from .infopigula import fetch_news_from_infopigula
        return await fetch_news_from_infopigula()


class NewsdataNewsSource(NewsSource):
    """Polish news from newsdata.io."""

    async def fetch_news(self) -> dict:
        from .newsdata import fetch_news_from_newsdata
        return await fetch_news_from_newsdata()


class NewsAPINewsSource(NewsSource):
    """US news from newsapi.org."""

    async def fetch_news(self) -> dict:
        from .newsapi import fetch_news_from_newsapi
        return await fetch_news_from_newsapi()


class StubNewsSource(NewsSource):
    """Placeholder for tenants whose news source is not yet implemented."""

    async def fetch_news(self) -> dict:
        return {
            "title": "[Stub] No news source configured for this tenant",
            "publish_date": "",
            "items": [],
        }


class CompositeNewsSource(NewsSource):
    """Merges items from multiple news sources into one combined feed."""

    def __init__(self, sources: list[NewsSource]):
        self._sources = sources

    async def fetch_news(self) -> dict:
        results = await asyncio.gather(
            *(s.fetch_news() for s in self._sources),
            return_exceptions=True,
        )

        all_items: list[dict] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("One news source failed in composite fetch: %s", result)
                continue
            all_items.extend(result.get("items", []))

        today = date.today().isoformat()
        return {
            "title": f"Combined News — {today}",
            "publish_date": today,
            "items": all_items,
        }


_SOURCES: dict[str, type[NewsSource]] = {
    "infopigula": InfoPigulaNewsSource,
    "newsdata": NewsdataNewsSource,
    "newsapi": NewsAPINewsSource,
    "stub": StubNewsSource,
}


def get_news_source(tenant: TenantConfig) -> NewsSource:
    key = tenant.news_source

    # Support composite sources: "infopigula+newsdata"
    if "+" in key:
        parts = [p.strip() for p in key.split("+")]
        sources: list[NewsSource] = []
        for part in parts:
            cls = _SOURCES.get(part)
            if cls is None:
                raise ValueError(
                    f"Unknown news_source '{part}' in composite '{key}' "
                    f"for tenant '{tenant.id}'. Available: {list(_SOURCES)}"
                )
            sources.append(cls())
        return CompositeNewsSource(sources)

    cls = _SOURCES.get(key)
    if cls is None:
        raise ValueError(
            f"Unknown news_source '{key}' for tenant '{tenant.id}'. "
            f"Available: {list(_SOURCES)}"
        )
    return cls()
