"""Rate limiting middleware for Lumina API endpoints.

Implements in-memory sliding window rate limiting per session and per client IP
to protect against bulk-push, flooding, and scraping attacks.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Dict, List, Tuple
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter per session_id and per IP address."""

    EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc", "/static")

    def __init__(
        self,
        app,
        max_requests_per_minute: int = 60,
        max_requests_per_hour: int = 600,
    ) -> None:
        super().__init__(app)
        self.max_per_minute = max_requests_per_minute
        self.max_per_hour = max_requests_per_hour
        # Maps key -> list of timestamp floats
        self._minute_buckets: Dict[str, List[float]] = defaultdict(list)
        self._hour_buckets: Dict[str, List[float]] = defaultdict(list)

    def _clean_and_check(self, key: str, now: float) -> Tuple[bool, int]:
        """Record a hit and check if rate limit is exceeded. Returns (is_allowed, retry_after)."""
        one_min_ago = now - 60.0
        one_hour_ago = now - 3600.0

        # Purge old timestamps
        min_hits = [t for t in self._minute_buckets[key] if t > one_min_ago]
        self._minute_buckets[key] = min_hits

        hour_hits = [t for t in self._hour_buckets[key] if t > one_hour_ago]
        self._hour_buckets[key] = hour_hits

        if len(min_hits) >= self.max_per_minute:
            oldest = min_hits[0]
            retry_after = max(1, int(60.0 - (now - oldest)))
            return False, retry_after

        if len(hour_hits) >= self.max_per_hour:
            oldest = hour_hits[0]
            retry_after = max(1, int(3600.0 - (now - oldest)))
            return False, retry_after

        # Record this request
        min_hits.append(now)
        hour_hits.append(now)
        return True, 0

    async def dispatch(self, request: Request, call_next):
        # Skip exempt prefixes
        if any(request.url.path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return await call_next(request)

        now = time.time()

        # Identify client by Session ID or IP address
        session_id = request.headers.get("X-Session-ID") or getattr(
            getattr(request, "state", None), "session_id", None
        )
        client_ip = request.client.host if request.client else "unknown"

        rate_key = f"session:{session_id}" if session_id else f"ip:{client_ip}"

        is_allowed, retry_after = self._clean_and_check(rate_key, now)
        if not is_allowed:
            logger.warning("Rate limit exceeded for %s. Retry-After: %ds", rate_key, retry_after)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down and try again later.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)


__all__ = ["RateLimiterMiddleware"]
