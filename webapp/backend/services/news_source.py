"""
News source abstraction — each tenant can have its own news provider.

Add new sources by:
1. Implementing a subclass of NewsSource
2. Registering it in _SOURCES and config/tenants.json
"""

from abc import ABC, abstractmethod

from ..config.tenant_registry import TenantConfig


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


_SOURCES: dict[str, type[NewsSource]] = {
    "infopigula": InfoPigulaNewsSource,
    "newsapi": NewsAPINewsSource,
    "stub": StubNewsSource,
}


def get_news_source(tenant: TenantConfig) -> NewsSource:
    cls = _SOURCES.get(tenant.news_source)
    if cls is None:
        raise ValueError(
            f"Unknown news_source '{tenant.news_source}' for tenant '{tenant.id}'. "
            f"Available: {list(_SOURCES)}"
        )
    return cls()
