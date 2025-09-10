"""
Simple rate limiting middleware.

This middleware imposes per‑client request limits over a rolling window.  It
tracks request timestamps for each client (identified by IP address) and
rejects requests that exceed the configured limit for the HTTP method.  The
limits can be tuned via the constructor.  Exceeding the limit results in a
429 response with a brief message.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 100, writes_per_minute: int = 30):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.writes_per_minute = writes_per_minute
        # Track timestamps of requests per client
        self.history: Dict[str, List[float]] = defaultdict(list)

    async def dispatch(self, request, call_next):  # type: ignore[override]
        # Determine the client key (IP address); fallback to 'anonymous'
        client = getattr(request, "client", None)
        key = client.host if client else "anonymous"
        now = time.time()
        limit = self.requests_per_minute
        # Treat mutating requests (POST/PUT/PATCH/DELETE) with a stricter quota
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            limit = self.writes_per_minute
        # Drop stale timestamps
        timestamps = [t for t in self.history[key] if t > now - 60]
        self.history[key] = timestamps
        if len(timestamps) >= limit:
            return PlainTextResponse(
                "Rate limit exceeded. Please wait before making more requests.",
                status_code=429,
            )
        timestamps.append(now)
        self.history[key] = timestamps
        return await call_next(request)