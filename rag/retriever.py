# rag/retriever.py
from __future__ import annotations

from typing import List, Dict, Any, Optional
import math
from pathlib import Path

import chromadb

from api.config import settings
from rag.embeddings import get_embedder
from rag.reranker import rerank


def get_chroma_client() -> chromadb.PersistentClient:
    """Return a global ChromaDB client using the legacy path.

    This is retained for health checks but embeddings for document retrieval are
    stored under per-collection directories via :func:`get_collection_client`.
    """
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)


def get_collection_client(collection_id: int) -> chromadb.PersistentClient:
    """Return a Chroma client scoped to a specific collection.

    Vectors for each collection live under ``data/chroma/coll_<cid>`` so that
    embeddings are isolated on disk.  This ensures RBAC rules can be enforced by
    only querying the namespaces a user is allowed to access.
    """
    base = Path(settings.chroma_persist_dir) / f"coll_{collection_id}"
    base.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(base))


def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    return num / (da * db + 1e-12)


def _rrf(rank_lists: List[List[str]], k: int = 60) -> Dict[str, float]:
    """Compute Reciprocal Rank Fusion scores for given ranking lists."""
    scores: Dict[str, float] = {}
    for lst in rank_lists:
        for rank, id_ in enumerate(lst):
            scores[id_] = scores.get(id_, 0.0) + 1.0 / (k + rank + 1)
    return scores


def _mmr(
    query_vec: List[float],
    cand_vecs: List[List[float]],
    cand_scores: List[float],
    k: int,
    lambda_mult: float = 0.5,
) -> List[int]:
    """
    Greedy Maximal Marginal Relevance (MMR) selection.
    Returns indices of selected candidates.
    """
    # Normalize input to plain Python lists to avoid numpy truthiness issues
    def _tolist(v):
        try:
            # numpy arrays or similar
            return v.tolist()  # type: ignore[attr-defined]
        except Exception:
            return list(v)

    cand_vecs = [_tolist(v) for v in cand_vecs]
    n = len(cand_vecs)
    if k <= 0 or n == 0:
        return []

    k = min(k, n)
    selected: List[int] = []
    remaining = list(range(n))

    # Start with the best candidate by score (higher is better)
    first = max(remaining, key=lambda i: cand_scores[i])
    selected.append(first)
    remaining.remove(first)

    while len(selected) < k and remaining:
        best_i = None
        best_val = float("-inf")
        for i in remaining:
            rel = cand_scores[i]
            # diversity = max cosine similarity to already selected items
            div = 0.0
            for j in selected:
                div = max(div, _cosine(cand_vecs[i], cand_vecs[j]))
            val = lambda_mult * rel - (1.0 - lambda_mult) * div
            if val > best_val:
                best_val = val
                best_i = i
        selected.append(best_i)  # type: ignore[arg-type]
        remaining.remove(best_i)  # type: ignore[arg-type]
    return selected

class Retriever:
    """Retriever that fans queries out to per-collection vector stores."""

    def __init__(self) -> None:
        self._embedder = get_embedder()

    def _embed_query(self, text: str) -> List[float]:
        text = " ".join(text.split())
        return self._embedder.embed_query(text)

    def search(
        self,
        query: str,
        k: int = 8,
        lambda_mult: Optional[float] = 0.5,
        fetch_multiplier: int = 3,
        allowed_collections: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k chunks for ``query`` with optional BM25, fusion and reranking."""

        if k <= 0:
            return []

        qvec = self._embed_query(query)
        n_results = max(k * max(1, fetch_multiplier), k)

        if not allowed_collections:
            return []

        # ---- Vector search ----
        vec_hits: List[Dict[str, Any]] = []
        for cid in allowed_collections:
            client = get_collection_client(cid)
            coll = client.get_or_create_collection(name="docs")
            res = coll.query(
                query_embeddings=[qvec],
                n_results=n_results,
                include=["documents", "metadatas", "embeddings", "distances"],
            )
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            embs = (res.get("embeddings") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            for doc, meta, emb, dist in zip(docs, metas, embs, dists):
                meta = {**meta, "collection_id": cid}
                vec_hits.append(
                    {
                        "id": meta.get("chunk_id", ""),
                        "text": doc,
                        "meta": meta,
                        "embedding": emb,
                        "vec_score": 1.0 - dist if dist is not None else 0.0,
                    }
                )

        vec_hits.sort(key=lambda h: h["vec_score"], reverse=True)
        vec_hits = vec_hits[:n_results]

        # ---- BM25 search ----
        bm25_hits: List[Dict[str, Any]] = []
        if settings.use_bm25:
            from rag import bm25

            for cid in allowed_collections:
                results = bm25.search(cid, query, n_results)
                for hit in results:
                    meta = {**hit["metadata"], "collection_id": cid}
                    bm25_hits.append(
                        {
                            "id": hit["id"],
                            "text": hit["text"],
                            "meta": meta,
                            "bm25_score": hit["score"],
                        }
                    )
            bm25_hits.sort(key=lambda h: h["bm25_score"], reverse=True)
            bm25_hits = bm25_hits[:n_results]

        # ---- Fuse with RRF ----
        if bm25_hits:
            rank_lists = [
                [h["id"] for h in vec_hits],
                [h["id"] for h in bm25_hits],
            ]
            rrf_scores = _rrf(rank_lists)
            combined: Dict[str, Dict[str, Any]] = {}
            for h in vec_hits:
                combined[h["id"]] = {
                    "text": h["text"],
                    "meta": h["meta"],
                    "embedding": h["embedding"],
                    "score": rrf_scores[h["id"]],
                }
            for h in bm25_hits:
                if h["id"] in combined:
                    combined[h["id"]]["score"] = rrf_scores[h["id"]]
                else:
                    combined[h["id"]] = {
                        "text": h["text"],
                        "meta": h["meta"],
                        "embedding": None,
                        "score": rrf_scores[h["id"]],
                    }
            fused_ids = sorted(combined, key=lambda x: combined[x]["score"], reverse=True)
        else:
            combined = {
                h["id"]: {
                    "text": h["text"],
                    "meta": h["meta"],
                    "embedding": h["embedding"],
                    "score": h["vec_score"],
                }
                for h in vec_hits
            }
            fused_ids = [h["id"] for h in vec_hits]

        fused_ids = fused_ids[:n_results]

        # Ensure embeddings are present and match query vector length
        target_dim = len(qvec)
        missing_ids = [
            i
            for i in fused_ids
            if combined[i]["embedding"] is None
            or len(combined[i]["embedding"]) != target_dim
        ]
        if missing_ids:
            texts_to_embed = [combined[i]["text"] for i in missing_ids]
            new_embs = self._embedder.embed(texts_to_embed)
            for i, emb in zip(missing_ids, new_embs):
                combined[i]["embedding"] = emb

        cand_docs = [combined[i]["text"] for i in fused_ids]
        cand_metas = [combined[i]["meta"] for i in fused_ids]
        cand_embs = [combined[i]["embedding"] for i in fused_ids]
        cand_scores = [combined[i]["score"] for i in fused_ids]

        if settings.use_reranker:
            cand_scores = rerank(query, cand_docs)

        have_embs = all(e is not None for e in cand_embs)
        if not have_embs:
            idx = list(range(len(cand_docs)))
            idx.sort(key=lambda i: cand_scores[i], reverse=True)
            keep = idx[:k]
        else:
            emb_list = [list(e) for e in cand_embs]
            if lambda_mult is None:
                idx = list(range(len(cand_docs)))
                idx.sort(key=lambda i: cand_scores[i], reverse=True)
                keep = idx[:k]
            else:
                keep = _mmr(qvec, emb_list, cand_scores, k, lambda_mult=lambda_mult)

        out: List[Dict[str, Any]] = []
        for i in keep:
            out.append(
                {
                    "text": cand_docs[i],
                    "metadata": cand_metas[i],
                    "score": cand_scores[i],
                }
            )
        return out
