"""Per-IP daily rate limit for real-backend query endpoints.

A public deployment defaults to the deterministic stub backend, but if
real backends are enabled the operator's API cost is exposed to anyone
who can reach the endpoint. This is a minimal in-memory guard — a fixed
per-IP daily cap on the query endpoints, reset at UTC midnight — meant
for a single-instance demo deployment, not a distributed production
rate limiter (which would need a shared store like Redis).
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_RATE_LIMITED_PATHS = ("/api/v1/query/run", "/api/v1/query/stream")


class DailyRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_per_day: int | None = None):
        super().__init__(app)
        self.max_per_day = max_per_day if max_per_day is not None else int(os.getenv("QUERY_RATE_LIMIT_PER_DAY", "50"))
        self._counts: dict[str, int] = defaultdict(int)
        self._day: str = self._today()

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async def dispatch(self, request: Request, call_next):
        if request.url.path not in _RATE_LIMITED_PATHS or self.max_per_day <= 0:
            return await call_next(request)

        today = self._today()
        if today != self._day:
            self._day = today
            self._counts.clear()

        client_ip = request.client.host if request.client else "unknown"
        self._counts[client_ip] += 1

        if self._counts[client_ip] > self.max_per_day:
            return JSONResponse(
                status_code=429,
                content={"error": "daily query limit exceeded for this deployment", "limit": self.max_per_day},
            )

        return await call_next(request)
