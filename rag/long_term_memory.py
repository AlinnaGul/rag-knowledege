from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from rag.embeddings import get_embedder
from .sql_store import SqlStore

@dataclass
class MemoryEntry:
    text: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    tags: Optional[List[str]] = None
    importance: float = 0.5

class LongTermMemory:
    def __init__(self, store: SqlStore) -> None:
        self.store = store
        self._emb = None

    def _embedder(self):
        if self._emb is None:
            self._emb = get_embedder()
        return self._emb

    def upsert(self, entries: List[MemoryEntry]) -> None:
        if not entries: return
        emb = self._embedder()
        payload: List[Dict[str, Any]] = []
        for i, e in enumerate(entries):
            mid = f"mem-{abs(hash((e.text, e.session_id, e.user_id)))%10_000_000}-{i}"
            payload.append({
                "id": mid,
                "text": e.text,
                "session_id": e.session_id,
                "user_id": e.user_id,
                "tags": e.tags or [],
                "importance": float(e.importance),
                "emb": emb.embed_query(e.text),
            })
        self.store.upsert_memories(payload)

    def search(self, query: str, top_k: int = 5, min_sim: float = 0.78) -> List[Dict[str, Any]]:
        if not query: return []
        qv = self._embedder().embed_query(query)
        scored = self.store.topk_similar_memories(qv, k=int(top_k))
        out: List[Dict[str, Any]] = []
        for score, item in scored:
            if score >= float(min_sim):
                out.append({"text": item["text"], "metadata": {
                    "session_id": item.get("session_id"),
                    "user_id": item.get("user_id"),
                    "tags": item.get("tags", []),
                    "importance": item.get("importance", 0.5),
                }, "score": score})
        return out
