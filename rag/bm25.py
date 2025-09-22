"""
Modular BM25 + Semantic Hybrid Search built on Whoosh + embeddings.

Components:
- SchemaFactory: Whoosh schema creation
- IndexManager: manage per-collection index lifecycle
- TextPreprocessor: normalize queries
- SemanticReranker: cosine rerank with pluggable embedder
- HybridSearcher: orchestrates BM25 search + optional semantic rerank

Back-compat helpers `index_chunks` and `search` are provided at bottom.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol
import json
import re

from whoosh import index, scoring
from whoosh.fields import Schema, ID, TEXT, STORED, NUMERIC
from whoosh.qparser import MultifieldParser

from api.config import settings
from rag.embeddings import get_embedder  # pluggable hybrid embedder

# --------------------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------------------

class SchemaFactory:
    @staticmethod
    def create() -> Schema:
        return Schema(
            chunk_id=ID(stored=True, unique=True),
            document_id=NUMERIC(stored=True, numtype=int),
            text=TEXT(stored=True),
            meta=STORED,
        )


# --------------------------------------------------------------------------------------
# Index management
# --------------------------------------------------------------------------------------

@dataclass
class IndexManager:
    base_dir: Path
    schema: Schema

    @classmethod
    def from_settings(cls) -> "IndexManager":
        base = Path(getattr(settings, "bm25_index_dir", "./data/bm25"))
        return cls(base_dir=base, schema=SchemaFactory.create())

    def _collection_path(self, collection_id: int) -> Path:
        return self.base_dir / f"coll_{collection_id}"

    def get_or_create(self, collection_id: int):
        path = self._collection_path(collection_id)
        path.mkdir(parents=True, exist_ok=True)
        if index.exists_in(str(path)):
            return index.open_dir(str(path))
        return index.create_in(str(path), self.schema)

    def writer(self, collection_id: int):
        ix = self.get_or_create(collection_id)
        return ix.writer()


# --------------------------------------------------------------------------------------
# Preprocessing
# --------------------------------------------------------------------------------------

class TextPreprocessor:
    _punct = re.compile(r"[^\w\s]")
    _space = re.compile(r"\s+")

    @classmethod
    def normalize(cls, query: str) -> str:
        q = (query or "").lower()
        q = cls._punct.sub(" ", q)
        q = cls._space.sub(" ", q).strip()
        return q


# --------------------------------------------------------------------------------------
# Embedding protocol & reranker
# --------------------------------------------------------------------------------------

class Embedder(Protocol):
    def embed_query(self, text: str) -> List[float]: ...


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = max(1e-8, sum(x * x for x in a) ** 0.5)
    nb = max(1e-8, sum(x * x for x in b) ** 0.5)
    return dot / (na * nb)


@dataclass
class SemanticReranker:
    embedder: Embedder
    top_k: int = 5

    def rerank(self, query: str, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not hits:
            return hits
        qvec = self.embedder.embed_query(query)
        top = hits[: self.top_k]
        # compute semantic scores using document embeddings via embed_query (fast path)
        for h in top:
            dvec = self.embedder.embed_query(h.get("text", ""))
            h["semantic_score"] = _cosine(qvec, dvec)
        top.sort(key=lambda x: x.get("semantic_score", 0.0), reverse=True)
        return top + hits[self.top_k :]


# --------------------------------------------------------------------------------------
# Hybrid searcher
# --------------------------------------------------------------------------------------

@dataclass
class HybridSearcher:
    index_mgr: IndexManager
    pre: TextPreprocessor
    reranker: Optional[SemanticReranker] = None

    def index_chunks(
        self,
        collection_id: int,
        doc_id: int,
        ids: List[str],
        texts: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        ix = self.index_mgr.get_or_create(collection_id)
        writer = ix.writer()
        # remove any prior content for this document
        writer.delete_by_term("document_id", int(doc_id))
        for cid, text, meta in zip(ids, texts, metadatas):
            writer.add_document(
                chunk_id=str(cid),
                document_id=int(doc_id),
                text=text,
                meta=json.dumps(meta or {}),
            )
        writer.commit()

    def search(
        self,
        collection_id: int,
        query: str,
        n_results: int = 10,
        use_semantic_rerank: bool = True,
    ) -> List[Dict[str, Any]]:
        ix = self.index_mgr.get_or_create(collection_id)
        norm_q = self.pre.normalize(query)
        qp = MultifieldParser(["text"], schema=ix.schema)
        q = qp.parse(norm_q)
        with ix.searcher(weighting=scoring.BM25F(B=0.75, K1=1.5)) as searcher:
            res = searcher.search(q, limit=n_results)
            hits: List[Dict[str, Any]] = []
            for hit in res:
                meta = json.loads(hit.get("meta", "{}"))
                hits.append(
                    {
                        "id": hit["chunk_id"],
                        "text": hit["text"],
                        "metadata": meta,
                        "score": float(hit.score),
                    }
                )
        if use_semantic_rerank and self.reranker is not None:
            hits = self.reranker.rerank(norm_q, hits)
        return hits


# --------------------------------------------------------------------------------------
# Back-compat procedural API
# --------------------------------------------------------------------------------------

# Singleton searcher using settings
_INDEX_MGR = IndexManager.from_settings()
_RERANKER = SemanticReranker(embedder=get_embedder(), top_k=5)
_SEARCHER = HybridSearcher(index_mgr=_INDEX_MGR, pre=TextPreprocessor, reranker=_RERANKER)


def index_chunks(
    collection_id: int,
    doc_id: int,
    ids: List[str],
    texts: List[str],
    metadatas: List[Dict[str, Any]],
) -> None:
    """Backwards-compatible indexing helper."""
    _SEARCHER.index_chunks(collection_id, doc_id, ids, texts, metadatas)


def search(
    collection_id: int,
    query: str,
    n_results: int = 10,
    semantic_rerank: bool = True,
    rerank_top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Backwards-compatible hybrid search helper."""
    # Update top_k on the fly if caller passes a different value
    if rerank_top_k != _RERANKER.top_k:
        _RERANKER.top_k = rerank_top_k
    return _SEARCHER.search(collection_id, query, n_results=n_results, use_semantic_rerank=semantic_rerank)
