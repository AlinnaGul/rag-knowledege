"""
Middleware to attach a disclaimer header to all API responses.

This middleware ensures that every response from the API contains a header
informing the caller that the information returned is for convenience only
and should not be considered authoritative.  By keeping the disclaimer in a
header we avoid polluting JSON response bodies while still communicating
important guardrails.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


DISCLAIMER_TEXT = (
    "Responses from this service are generated for convenience and may "
    "contain inaccuracies. Always consult official sources for critical decisions."
)


class DisclaimerMiddleware(BaseHTTPMiddleware):
    """Middleware that adds a disclaimer header to each response."""

    async def dispatch(self, request: Scope, call_next):  # type: ignore[override]
        response = await call_next(request)
        # Add disclaimer header if not already present
        response.headers.setdefault("X-Disclaimer", DISCLAIMER_TEXT)
        return response