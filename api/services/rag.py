"""
Service layer for running the RAG pipeline end to end.

This module ties together the rewriter, retriever and answerer to answer user
questions.  It also logs queries and records basic metrics such as latency and
token usage.
"""
from __future__ import annotations

from typing import Optional, List
import datetime as _dt
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..query_logger import log_query
from .titles import generate_session_title
from rag.retriever import Retriever
from rag.answerer import generate_answer, rewrite_question
from rag.guardrails import is_safe, DEFAULT_REFUSAL, safe_response
from . import memory as memory_service



def ask_question(
    db: Session,
    user: models.User,
    question: str,
    session_id: int,
    top_k: Optional[int] = None,
    temperature: Optional[float] = None,
    mmr_lambda: Optional[float] = None,
    allowed_collections: Optional[List[int]] = None,
) -> dict:
    """Run the full agentic RAG pipeline to answer a question.

    Parameters:
        db: database session for logging queries
        user: the user asking the question
        question: the natural language question
        top_k: optional override for number of context chunks to retrieve
        temperature: optional override for answer generation temperature

    Returns:
        A dictionary containing the answer, citations and follow‑up suggestions.
    """
    if allowed_collections is not None and len(allowed_collections) == 0:
        return {"answer": "", "citations": [], "followups": []}

    # Basic safety check before hitting the LLM
    if not is_safe(question):
        query_log = models.Query(
            user_id=user.id,
            question=question,
            answer=DEFAULT_REFUSAL,
            answer_len=len(DEFAULT_REFUSAL),
            tokens_in=None,
            tokens_out=None,
            latency_ms=0,
        )
        db.add(query_log)
        db.flush()
        history_row = models.ChatHistory(
            user_id=user.id,
            session_id=session_id,
            query=question,
            response=DEFAULT_REFUSAL,
            query_id=query_log.id,
        )
        db.add(history_row)
        sess = db.get(models.ChatSession, session_id)
        if sess:
            if not sess.session_title or sess.session_title == "New Chat":
                sess.session_title = generate_session_title(question)
            sess.updated_at = _dt.datetime.utcnow()
        db.commit()
        log_query(query_log.id, user.id, question, DEFAULT_REFUSAL)
        return {
            "answer": DEFAULT_REFUSAL,
            "citations": [],
            "followups": [],
            "query_id": query_log.id,
        }

    # Load recent conversation for short-term memory
    history_rows = (
        db.query(models.ChatHistory)
        .filter(
            models.ChatHistory.user_id == user.id,
            models.ChatHistory.session_id == session_id,
        )
        .order_by(models.ChatHistory.created_at.asc())
        .all()
    )
    history = [
        {"question": h.query, "answer": h.response} for h in history_rows[-5:]
    ]

    # Step 1: rewrite question to improve recall
    rewritten = rewrite_question(question)
    # Step 2: retrieve relevant chunks
    retriever = Retriever()
    k = top_k or settings.top_k
    results = retriever.search(
        rewritten,
        k=k,
        lambda_mult=mmr_lambda or settings.mmr_lambda,
        allowed_collections=allowed_collections,
    )
    had_docs = bool(results)

    # Load any persisted user memories and append them to the retrieval results.
    try:
        mems = memory_service.load_memories(db, user.id)
        # Cap the number of memories appended to avoid overwhelming the context
        results.extend(mems[: max(0, k // 2)])
    except Exception:
        pass
    # Step 3: generate answer using original question (for user readability)
    answer_data = generate_answer(
        question, results, temperature=temperature, history=history
    )

    if not had_docs:
        answer_data["citations"] = []

    # Moderation on the generated answer
    answer_data["answer"] = safe_response(answer_data["answer"])
    # Step 4: log query and chat history
    query_log = models.Query(
        user_id=user.id,
        question=question,
        answer=answer_data["answer"],
        answer_len=len(answer_data["answer"]),
        tokens_in=None,
        tokens_out=None,
        latency_ms=answer_data.get("latency_ms"),
    )
    db.add(query_log)
    db.flush()
    history_row = models.ChatHistory(
        user_id=user.id,
        session_id=session_id,
        query=question,
        response=answer_data["answer"],
        query_id=query_log.id,
    )
    db.add(history_row)
    sess = db.get(models.ChatSession, session_id)
    if sess:
        if not sess.session_title or sess.session_title == "New Chat":
            sess.session_title = generate_session_title(question)
        sess.updated_at = _dt.datetime.utcnow()
    db.commit()
    log_query(query_log.id, user.id, question, answer_data["answer"])

    # Persist the question/answer pair into long‑term user memory for future
    # retrieval.  Errors are swallowed to avoid surfacing DB issues to the user.
    try:
        memory_service.save_memory(db, user.id, key=question.strip(), value=answer_data["answer"])  # type: ignore[arg-type]
    except Exception:
        pass
    return {
        "answer": answer_data["answer"],
        "citations": answer_data["citations"],
        "followups": [],
        "query_id": query_log.id,
    }
