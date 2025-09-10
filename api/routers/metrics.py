"""
Metrics endpoints and utilities.

This module exposes a simple metrics endpoint at `/api/metrics` returning
cumulative request counts per path since the application started.  It relies
on a middleware to increment counts for each incoming request.
"""
from __future__ import annotations

from collections import Counter
from fastapi import APIRouter


# Global counter of requests per path
request_counts: Counter[str] = Counter()

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metrics")
def metrics() -> dict[str, int]:
    """Return the cumulative number of requests handled per endpoint path."""
    # Return a plain dict for JSON serialisation
    return dict(request_counts)