"""Routes for managing chat sessions and their history."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from ..deps import get_db, get_current_user
from .. import models, schemas


router = APIRouter(prefix="/api/chat/sessions", tags=["chat_sessions"])


@router.post("", response_model=schemas.ChatSession)
def create_session(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    session = models.ChatSession(user_id=current_user.id, session_title="New Chat")
    db.add(session)
    db.commit(); db.refresh(session)
    return session


@router.get("", response_model=List[schemas.ChatSession])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    last_subq = (
        db.query(
            models.ChatHistory.session_id.label("s_id"),
            func.max(models.ChatHistory.created_at).label("last_time"),
        )
        .group_by(models.ChatHistory.session_id)
        .subquery()
    )

    last_hist = aliased(models.ChatHistory)

    rows = (
        db.query(models.ChatSession, last_hist)
        .outerjoin(last_subq, models.ChatSession.id == last_subq.c.s_id)
        .outerjoin(
            last_hist,
            (last_hist.session_id == models.ChatSession.id)
            & (last_hist.created_at == last_subq.c.last_time),
        )
        .filter(models.ChatSession.user_id == current_user.id)
        .order_by(models.ChatSession.updated_at.desc())
        .all()
    )

    return [
        schemas.ChatSession(
            id=sess.id,
            session_title=sess.session_title,
            created_at=sess.created_at,
            updated_at=sess.updated_at,
            last_message=hist.query if hist else None,
            last_message_at=hist.created_at if hist else None,
        )
        for sess, hist in rows
    ]


@router.get("/{session_id}/history", response_model=List[schemas.ChatEntry])
def get_history(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    sess = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.id == session_id, models.ChatSession.user_id == current_user.id)
        .first()
    )
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    rows = (
        db.query(models.ChatHistory, models.Query.feedback)
        .outerjoin(models.Query, models.ChatHistory.query_id == models.Query.id)
        .filter(models.ChatHistory.session_id == session_id)
        .order_by(models.ChatHistory.created_at.asc())
        .all()
    )
    return [
        schemas.ChatEntry(
            id=hist.id,
            query=hist.query,
            response=hist.response,
            created_at=hist.created_at,
            session_id=hist.session_id,
            query_id=hist.query_id,
            feedback=fb,
        )
        for hist, fb in rows
    ]


@router.patch("/{session_id}", response_model=schemas.ChatSession)
def rename_session(
    session_id: int,
    payload: schemas.ChatSessionUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    sess = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.id == session_id, models.ChatSession.user_id == current_user.id)
        .first()
    )
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    sess.session_title = payload.session_title
    db.commit(); db.refresh(sess)
    return sess


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    sess = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.id == session_id, models.ChatSession.user_id == current_user.id)
        .first()
    )
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    db.delete(sess)
    db.commit()
    return None

