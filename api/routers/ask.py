"""
Question answering endpoint.

Authenticated users can post questions and receive answers with citations.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..schemas import AskRequest, AskResponse
from ..deps import get_db, get_current_user, get_allowed_collection_ids
from ..services import rag as rag_service, docs as docs_service
from ..audit import log_action
from .. import models


router = APIRouter(prefix="/api/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
def ask(
    req: AskRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    allowed: List[int] = Depends(get_allowed_collection_ids),
):
    """Answer a user's question using the RAG pipeline."""
    if not allowed and current_user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access Denied")
    total_emb = docs_service.total_embeddings_for_collections(db, allowed)
    if total_emb == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No indexed documents for this user",
        )
    sess_id = req.session_id
    sess = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.id == sess_id, models.ChatSession.user_id == current_user.id)
        .first()
    )
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    result = rag_service.ask_question(
        db=db,
        user=current_user,
        question=req.question,
        top_k=req.top_k,
        temperature=req.temperature,
        mmr_lambda=req.mmr_lambda,
        allowed_collections=allowed,
        session_id=sess_id,
    )
    log_action("query", user_id=current_user.id, collection_id=allowed)
    return AskResponse(
        answer=result["answer"],
        citations=result["citations"],
        followups=result.get("followups", []),
        query_id=result["query_id"],
    )
