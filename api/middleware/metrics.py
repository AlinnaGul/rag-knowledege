"""
Middleware to record simple per‑path request metrics.

Every incoming HTTP request increments a counter keyed by the request path.  The
counters live in `api.routers.metrics.request_counts` and are exposed via the
`/api/metrics` endpoint.  This lightweight approach enables basic monitoring
without external dependencies.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Scope
from . import rate_limit  # noqa: F401  # ensure RateLimitMiddleware is imported

from api.routers.metrics import request_counts


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Scope, call_next):  # type: ignore[override]
        try:
            path = request.get("path") or request.get("raw_path") or b""
            # raw_path is bytes, convert to string if needed
            if isinstance(path, bytes):
                path_str = path.decode("latin-1", errors="ignore")
            else:
                path_str = str(path)
            request_counts[path_str] += 1
        except Exception:
            pass
        return await call_next(request)