"""
Simple in-memory cache with TTL for S3 data.

Cache is invalidated when any mutation occurs, ensuring no stale data.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Optional
import threading


@dataclass
class CacheEntry:
    """A cached value with expiration time."""
    value: Any
    expires_at: float


class RunsCache:
    """
    Thread-safe in-memory cache for runs data.

    Cache keys:
    - "runs_list" - the list of all run summaries
    - "run:{run_id}" - individual run details
    """

    def __init__(self, default_ttl: float = 900.0):  # 15 minutes default (was 5)
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        # Separate TTL for runs list (can be longer since it's expensive to compute)
        self._runs_list_ttl = 1800.0  # 30 minutes for runs list

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache, returns None if expired or missing."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() > entry.expires_at:
                del self._cache[key]
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Set a value in cache with TTL.

        Uses longer TTL for runs_list since it's expensive to compute.
        """
        if ttl is None:
            ttl = self._runs_list_ttl if key.startswith("runs_list:") else self._default_ttl
        with self._lock:
            self._cache[key] = CacheEntry(
                value=value,
                expires_at=time.time() + ttl
            )

    def delete(self, key: str) -> None:
        """Delete a specific key from cache."""
        with self._lock:
            self._cache.pop(key, None)

    def invalidate_run(self, run_id: str, tenant_prefix: str = None) -> None:
        """
        Invalidate cache for a specific run.
        Also invalidates the runs list since run state may have changed.
        tenant_prefix: pass explicitly from background tasks where ContextVar may not be set.
        """
        if tenant_prefix is None:
            from ..core.storage_config import get_tenant_prefix
            tenant_prefix = get_tenant_prefix()
        with self._lock:
            self._cache.pop(f"run:{tenant_prefix}:{run_id}", None)
            self._cache.pop(f"runs_list:{tenant_prefix}", None)

    def invalidate_runs_list(self, tenant_prefix: str = None) -> None:
        """Invalidate just the runs list cache."""
        if tenant_prefix is None:
            from ..core.storage_config import get_tenant_prefix
            tenant_prefix = get_tenant_prefix()
        with self._lock:
            self._cache.pop(f"runs_list:{tenant_prefix}", None)

    def invalidate_all(self) -> None:
        """Clear the entire cache."""
        with self._lock:
            self._cache.clear()

    def stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            now = time.time()
            valid = sum(1 for e in self._cache.values() if e.expires_at > now)
            return {
                "total_entries": len(self._cache),
                "valid_entries": valid,
                "expired_entries": len(self._cache) - valid,
            }


# Global cache instance
_cache = RunsCache()


def get_cache() -> RunsCache:
    """Get the global cache instance."""
    return _cache
