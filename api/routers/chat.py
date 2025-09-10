"""Streaming chat endpoint."""
from __future__ import annotations

import asyncio
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user, get_allowed_collection_ids
from ..schemas import AskRequest
from ..services import rag as rag_service, prefs as prefs_service, docs as docs_service
from ..audit import log_action
from .. import models

router = APIRouter(prefix="/api/chat", tags=["chat"])


async def _stream_answer(text: str, meta: dict):
    try:
        for token in text.split():
            yield f"data: {json.dumps({'delta': token + ' '})}\n\n"
            await asyncio.sleep(0)
        yield f"event: end\ndata: {json.dumps(meta)}\n\n"
    except asyncio.CancelledError:
        # client disconnected; suppress cancellation noise
        return


@router.post("/messages")
async def chat_messages(
    req: AskRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    allowed: list[int] = Depends(get_allowed_collection_ids),
):
    if not allowed and current_user.role not in ("admin", "superadmin"):
        async def no_sources():
            yield "event: end\ndata: {\"reason\": \"Access Denied\"}\n\n"
        return StreamingResponse(no_sources(), media_type="text/event-stream")
    total_emb = docs_service.total_embeddings_for_collections(db, allowed)
    if total_emb == 0:
        async def no_indexed():
            yield "event: end\ndata: {\"reason\": \"No indexed documents for this user\"}\n\n"
        return StreamingResponse(no_indexed(), media_type="text/event-stream")

    sess = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.id == req.session_id, models.ChatSession.user_id == current_user.id)
        .first()
    )
    if not sess:
        async def no_session():
            yield "event: end\ndata: {\"reason\": \"Session not found\"}\n\n"
        return StreamingResponse(no_session(), media_type="text/event-stream")
    prefs = prefs_service.get_prefs(db, current_user.id)
    result = rag_service.ask_question(
        db=db,
        user=current_user,
        question=req.question,
        top_k=prefs.top_k,
        temperature=prefs.temperature,
        mmr_lambda=prefs.mmr_lambda,
        allowed_collections=allowed,
        session_id=req.session_id,
    )
    log_action("query", user_id=current_user.id, collection_id=allowed)

    meta = {
        "temperature": prefs.temperature,
        "topK": prefs.top_k,
        "mmrLambda": prefs.mmr_lambda,
        "usedCollections": allowed,
        "query_id": result["query_id"],
    }
    return StreamingResponse(
        _stream_answer(result["answer"], meta), media_type="text/event-stream"
    )
