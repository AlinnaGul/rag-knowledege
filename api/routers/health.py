"""
Healthcheck endpoints.

`/api/health` returns 200 OK if the app is up.
`/api/ready` runs a basic readiness check: DB + Chroma reachable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..deps import get_db
from rag.retriever import get_chroma_client

router = APIRouter(prefix="/api", tags=["health"])

@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    # DB
    from sqlalchemy import text
    db.execute(text("SELECT 1"))

    # Chroma
    client = get_chroma_client()
    client.list_collections()
    return {"status": "ready"}


@router.get("/health")
def health():
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness probe; checks DB and Chroma connectivity."""
    # DB check
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc}",
        )
    # Chroma check
    try:
        client = get_chroma_client()
        client.list_collections()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chroma unavailable: {exc}",
        )
    return {"status": "ready"}


@router.get("/health/details")
def health_details(db: Session = Depends(get_db)):
    """Extended health with individual subsystem flags."""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    try:
        client = get_chroma_client()
        client.list_collections()
        chroma_ok = True
    except Exception:
        chroma_ok = False

    payload = {
        "database": db_ok,
        "chroma": chroma_ok,
        "status": "ok" if (db_ok and chroma_ok) else "degraded",
    }
    if db_ok and chroma_ok:
        return payload
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=payload)
