"""
Middleware for assigning correlation IDs to incoming requests.

This module defines a Starlette `BaseHTTPMiddleware` subclass that injects a
unique UUID into a context variable for each request.  Downstream loggers can
access this value to correlate log entries belonging to the same request.  The
correlation ID is also returned to clients via the `X-Request-ID` response
header.
"""
from __future__ import annotations

import uuid
import contextvars
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Scope

# Context variable to hold the current request ID
request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware that sets a unique request ID for each request."""

    async def dispatch(self, request: Scope, call_next):  # type: ignore[override]
        rid = str(uuid.uuid4())
        # Store the ID in a context variable
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
        finally:
            # Reset the context variable to previous state to avoid leaking
            request_id_ctx.reset(token)
        response.headers.setdefault("X-Request-ID", rid)
        return response