"""Routes for query feedback."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user
from .. import models
from ..query_logger import log_feedback

router = APIRouter(prefix="/api/queries", tags=["queries"])


@router.post("/{query_id}/feedback", status_code=204)
def set_feedback(
    query_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    feedback = payload.get("feedback")
    if feedback not in {"up", "down"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid feedback")
    q = db.query(models.Query).filter(models.Query.id == query_id, models.Query.user_id == current_user.id).first()
    if not q:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")
    q.feedback = feedback
    db.commit()
    log_feedback(query_id, current_user.id, feedback)
    return None


