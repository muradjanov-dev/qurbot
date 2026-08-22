"""A small in-process rate limiter for the storefront's expensive endpoints.

Parsing a list and optimizing a basket both cost real work -- a catalogue
search per line, possibly an LLM call, then the solver -- and both are reachable
without signing in. This keeps one visitor from spending the whole box's budget.

Deliberately per-process rather than the bot's Redis sliding window: the web
must keep serving pages when Redis is unavailable, and an approximate limit
enforced everywhere beats an exact one that can take the site down. Redis is
the upgrade path if a single replica's share ever becomes too generous.
"""

from __future__ import annotations

import time
from collections import deque

from fastapi import Request

from app.db.models.user import User

# Stop the key table from growing without bound if a caller cycles addresses.
_MAX_TRACKED_KEYS = 10_000


class SlidingWindow:
    """Allow at most `limit` hits per key within `window_seconds`."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, *, now: float | None = None) -> bool:
        current = now if now is not None else time.monotonic()
        cutoff = current - self.window_seconds

        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= _MAX_TRACKED_KEYS:
                self._evict(cutoff)
            hits = deque()
            self._hits[key] = hits

        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            return False

        hits.append(current)
        return True

    def _evict(self, cutoff: float) -> None:
        """Drop keys whose window has fully elapsed."""
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]
        if not stale:
            # Nothing has aged out yet: clear the table rather than refuse new
            # callers. Losing a partial window is a smaller failure than
            # locking out everyone who arrives next.
            self._hits.clear()


def client_key(request: Request, user: User | None) -> str:
    """Who to charge this request to: the account when known, else the address."""
    if user is not None:
        return f"user:{user.id}"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"
