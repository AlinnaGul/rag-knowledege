"""
Question answering & retrieval preview endpoints.

Authenticated users can post questions and receive answers with citations.
Preview endpoints expose raw retrieval results (useful for tuning).
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import models
from ..audit import log_action
from ..config import settings
from ..deps import get_current_user, get_db, get_allowed_collection_ids
from ..schemas import AskRequest, AskResponse
from ..services import docs as docs_service
from ..services import rag as rag_service
from rag.retriever import NonLinearRetriever, RetrievalConfig, RetrievalStrateg

# Direct access to retriever for preview & model-info
from rag.retriever import (
    NonLinearRetriever,
    RetrievalConfig,
    RetrievalStrategy,
    create_multimodal_config,
    get_model_status as retriever_model_status,
)
_retriever = NonLinearRetriever()
# Optional MLflow (never blocks requests)
try:
    import mlflow  # type: ignore
    _MLFLOW_AVAILABLE = True
except Exception:  # pragma: no cover
    mlflow = None  # type: ignore
    _MLFLOW_AVAILABLE = False

# Optional telemetry wrappers (safe if missing)
try:
    from api.telemetry.mlflow import (
        start_run as mlflow_start_run,
        log_params as mlflow_log_params,
        log_metrics as mlflow_log_metrics,
        log_json_artifact as mlflow_log_json_artifact,
        log_rag_artifacts,
        log_preview_artifacts,
    )
    _TELEMETRY_HELPERS = True
except Exception:
    _TELEMETRY_HELPERS = False

router = APIRouter(prefix="/api/ask", tags=["ask"])

# Reuse a single retriever instance for preview/model-info
_retriever = NonLinearRetriever()


# --------------------------------------------------------------------------------------
# /api/ask : Full RAG answer (same response model your app already uses)
# --------------------------------------------------------------------------------------
@router.post("", response_model=AskResponse)
def ask(
    req: AskRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    allowed: List[int] = Depends(get_allowed_collection_ids),
):
    """Answer a user's question using the RAG pipeline (+citations)."""
    if not allowed and current_user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access Denied")

    # Ensure content exists for these collections
    total_emb = docs_service.total_embeddings_for_collections(db, allowed)
    if total_emb == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No indexed documents for this user",
        )

    # Validate chat session
    sess = (
        db.query(models.ChatSession)
        .filter(
            models.ChatSession.id == req.session_id,
            models.ChatSession.user_id == current_user.id,
        )
        .first()
    )
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Run RAG service (kept as-is in your project)
    t0 = time.time()
    result = rag_service.ask_question(
        db=db,
        user=current_user,
        question=req.question,
        top_k=req.top_k,
        temperature=req.temperature,
        mmr_lambda=req.mmr_lambda,
        allowed_collections=allowed,
        session_id=req.session_id,
    )
    latency_ms = int(result.get("latency_ms") or (time.time() - t0) * 1000)

    # Audit
    log_action("query", user_id=current_user.id, collection_id=allowed)

    # Optional telemetry
    if _MLFLOW_AVAILABLE:
        try:
            run_name = f"ask:{req.session_id}"
            tags = {
                "route": "/api/ask",
                "domain": getattr(settings, "domain", "default"),
                "user_role": current_user.role,
                "user_id": str(current_user.id),
                "app_version": "0.1.0",
            }

            if _TELEMETRY_HELPERS:
                with mlflow_start_run(run_name=run_name, tags=tags) as mlf:
                    log_rag_artifacts(
                        mlf,
                        req=req,
                        result=result,
                        user_id=current_user.id,
                        allowed_collections=allowed,
                        session_id=req.session_id,
                    )
            else:
                mlflow.set_tag("route", tags["route"])  # type: ignore[attr-defined]
                mlflow.set_tag("domain", tags["domain"])  # type: ignore[attr-defined]
                mlflow.set_tag("user_role", tags["user_role"])  # type: ignore[attr-defined]
                mlflow.set_tag("user_id", tags["user_id"])  # type: ignore[attr-defined]
                mlflow.set_tag("app_version", tags["app_version"])  # type: ignore[attr-defined]
                with mlflow.start_run(run_name=run_name, nested=True):  # type: ignore[attr-defined]
                    mlflow.log_params(  # type: ignore[attr-defined]
                        {
                            "top_k": req.top_k,
                            "temperature": req.temperature,
                            "mmr_lambda": req.mmr_lambda,
                            "collections": ",".join(map(str, allowed or [])),
                        }
                    )
                    mlflow.log_metrics(  # type: ignore[attr-defined]
                        {
                            "latency_ms_total": float(latency_ms),
                            "confidence": float(result.get("confidence", 0.0)),
                            "answer_chars": float(len(result.get("answer", "") or "")),
                            "n_citations": float(len(result.get("citations", []) or [])),
                        }
                    )
                    payload = {
                        "question": req.question,
                        "session_id": req.session_id,
                        "answer": result.get("answer"),
                        "citations": result.get("citations", []),
                        "followups": result.get("followups", []),
                        "query_id": result.get("query_id"),
                        "candidates": result.get("candidates", []),
                        "retrieval": result.get("retrieval", {}),
                    }
                    try:
                        mlflow.log_dict(payload, "ask_result.json")  # type: ignore[attr-defined]
                    except Exception:
                        mlflow.log_text(json.dumps(payload, ensure_ascii=False, indent=2), "ask_result.json")  # type: ignore[attr-defined]
        except Exception:
            pass  # never block

    return AskResponse(
        answer=result["answer"],
        citations=result["citations"],
        followups=result.get("followups", []),
        query_id=result["query_id"],
    )


# --------------------------------------------------------------------------------------
# NEW: retrieval-only preview (no LLM synthesis) for quick debugging/tuning
# --------------------------------------------------------------------------------------
class PreviewRequest(BaseModel):
    question: str = Field(..., min_length=2)
    top_k: int = Field(8, ge=1, le=50, description="Final results to return")
    fetch_multiplier: int = Field(3, ge=1, le=10, description="Over-fetch factor before MMR/rerank")
    mmr_lambda: Optional[float] = Field(0.5, ge=0.0, le=1.0, description="MMR diversity")
    use_mmr: bool = True
    use_reranker: bool = True
    strategy: Optional[RetrievalStrategy] = Field(None, description="Force strategy; default ADAPTIVE")
    query_expansion_factor: int = Field(3, ge=1, le=10)
    graph_depth: int = Field(2, ge=1, le=5)


class PreviewHit(BaseModel):
    text: str
    metadata: Dict[str, Any]
    score: float
    retrieval_method: str
    expanded_queries: List[str] = []
    graph_path: List[str] = []


class PreviewResponse(BaseModel):
    results: List[PreviewHit]


@router.post("/preview", response_model=PreviewResponse)
def preview_retrieval(
    req: PreviewRequest,
    current_user: models.User = Depends(get_current_user),
    allowed: List[int] = Depends(get_allowed_collection_ids),
):
    """
    Return the top-k retrieved chunks WITHOUT running the LLM answerer.
    Uses NonLinearRetriever with strategy/MMR/reranker/expansion/graph options.
    """
    if not allowed and current_user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access Denied")

    cfg = RetrievalConfig(
        k=req.top_k,
        lambda_mult=req.mmr_lambda,
        fetch_multiplier=req.fetch_multiplier,
        use_mmr=req.use_mmr,
        use_reranker=req.use_reranker,
        strategy=req.strategy or RetrievalStrategy.ADAPTIVE,
        query_expansion_factor=req.query_expansion_factor,
        graph_depth=req.graph_depth,
    )

    results = _retriever.search(
        query=req.question,
        config=cfg,
        allowed_collections=allowed,
    )

    # Optional telemetry
    if _TELEMETRY_HELPERS:
        try:
            with mlflow_start_run(
                run_name=f"preview:{current_user.id}",
                tags={"route": "/api/ask/preview"},
            ) as mlf:
                log_preview_artifacts(mlf, req=req, results=results, allowed_collections=allowed)
        except Exception:
            pass

    return PreviewResponse(
        results=[
            PreviewHit(
                text=r.text,
                metadata=r.metadata,
                score=r.score,
                retrieval_method=r.retrieval_method,
                expanded_queries=getattr(r, "expanded_queries", []),
                graph_path=getattr(r, "graph_path", []),
            )
            for r in results
        ]
    )


# Small helpers to make UI/API testing easier
@router.get("/strategies", response_model=List[str])
def list_strategies():
    """List supported retrieval strategies."""
    return [s.value for s in RetrievalStrategy]


@router.get("/models/status")
def model_status():
    """Quick view of which optional model stacks are available at runtime."""
    return retriever_model_status()



# --- add after the existing /api/ask endpoint ---
class PreviewRequest(BaseModel):
    question: str
    top_k: int = 8
    fetch_multiplier: int = 3
    mmr_lambda: float | None = 0.5
    use_mmr: bool = True
    use_reranker: bool = True
    strategy: RetrievalStrategy | None = None
    query_expansion_factor: int = 3
    graph_depth: int = 2

class PreviewHit(BaseModel):
    text: str
    metadata: Dict[str, Any]
    score: float
    retrieval_method: str
    expanded_queries: List[str] = []
    graph_path: List[str] = []

class PreviewResponse(BaseModel):
    results: List[PreviewHit]

@router.post("/preview", response_model=PreviewResponse)
def preview_retrieval(
    req: PreviewRequest,
    current_user: models.User = Depends(get_current_user),
    allowed: List[int] = Depends(get_allowed_collection_ids),
):
    if not allowed and current_user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access Denied")

    cfg = RetrievalConfig(
        k=req.top_k,
        lambda_mult=req.mmr_lambda,
        fetch_multiplier=req.fetch_multiplier,
        use_mmr=req.use_mmr,
        use_reranker=req.use_reranker,
        strategy=req.strategy or RetrievalStrategy.ADAPTIVE,
        query_expansion_factor=req.query_expansion_factor,
        graph_depth=req.graph_depth,
    )

    results = _retriever.search(req.question, cfg, allowed)
    return PreviewResponse(
        results=[
            PreviewHit(
                text=r.text,
                metadata=r.metadata,
                score=r.score,
                retrieval_method=r.retrieval_method,
                expanded_queries=getattr(r, "expanded_queries", []),
                graph_path=getattr(r, "graph_path", []),
            )
            for r in results
        ]
    )

@router.get("/strategies", response_model=List[str])
def list_strategies():
    return [s.value for s in RetrievalStrategy]
