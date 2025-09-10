from __future__ import annotations

"""Utility for loading an optional cross-encoder re-ranker."""

from typing import List

from api.config import settings

try:  # pragma: no cover - optional dependency
    from sentence_transformers import CrossEncoder
except Exception:  # pragma: no cover
    CrossEncoder = None  # type: ignore

_reranker = None


def get_reranker():
    """Return a cached CrossEncoder instance if enabled and available."""
    global _reranker
    if _reranker is None and settings.use_reranker and CrossEncoder is not None:
        try:
            _reranker = CrossEncoder(
                settings.reranker_model,
                device="cpu",
            )
        except Exception:  # pragma: no cover - dependency issues
            _reranker = None
    return _reranker


def rerank(query: str, texts: List[str]) -> List[float]:
    """Return relevance scores for ``texts`` given ``query`` using the cross-encoder."""
    model = get_reranker()
    if model is None:
        return [0.0] * len(texts)
    pairs = [(query, t) for t in texts]
    scores = model.predict(pairs)
    try:
        return scores.tolist()  # type: ignore[union-attr]
    except Exception:  # pragma: no cover - already a list
        return list(scores)
