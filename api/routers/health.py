"""
Healthcheck endpoints.

`/api/health` returns 200 OK if the app is up.  `/api/ready` runs a basic
readiness check by ensuring the database and vector store are reachable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_db
# AFTER
from rag.retriever import get_chroma_client



router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness probe; checks DB and Chroma connectivity."""
    # Check DB connectivity by executing a simple statement
    try:
        db.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Database unavailable: {exc}")
    # Check Chroma client initialization
    try:
        client = get_chroma_client()
        # Optionally list collections
        client.list_collections()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Chroma unavailable: {exc}")
    return {"status": "ready"}


@router.get("/health/details")
def health_details(db: Session = Depends(get_db)):
    """
    Extended health endpoint exposing database and Chroma connectivity status.

    Returns a JSON object containing boolean flags for each subsystem.  If
    either subsystem is unavailable a 503 error is returned.
    """
    # Check DB
    try:
        db.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    # Check Chroma
    try:
        client = get_chroma_client()
        client.list_collections()
        chroma_ok = True
    except Exception:
        chroma_ok = False
    status_code = status.HTTP_200_OK if (db_ok and chroma_ok) else status.HTTP_503_SERVICE_UNAVAILABLE
    return {"database": db_ok, "chroma": chroma_ok, "status": "ok" if status_code == 200 else "degraded"}