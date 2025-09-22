from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

from rag.embeddings import get_embedder
from .sql_store import SqlStore

class ShortTermMemory:
    def __init__(self, store: SqlStore, max_items: int = 30) -> None:
        self.store = store
        self.max_items = int(max_items)
        self._emb = None

    def _embedder(self):
        if self._emb is None:
            self._emb = get_embedder()
        return self._emb

    def add(self, session_id: str, user_input: str, answer: str) -> None:
        vec = self._embedder().embed_query(user_input)
        self.store.add_interaction(session_id, user_input, answer, vec)

    def recent(self, session_id: str, n: int = 5) -> List[Dict[str, Any]]:
        return self.store.recent_interactions(session_id, n)

    def find_similar(self, session_id: str, query: str, top_k: int = 1) -> List[Tuple[float, Dict[str, Any]]]:
        qv = self._embedder().embed_query(query)
        best = self.store.most_similar_interaction(session_id, qv)
        return [best] if best else []
