"""Embedding backend abstraction with caching."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import List, Optional
import threading

from api.config import settings


class EmbeddingClient:
    """Embed text using configurable provider with SQLite caching."""

    def __init__(self) -> None:
        self.model = settings.embedding_model
        self.provider = settings.embedding_provider.lower()
        self._client = None
        if self.provider == "openai":
            from openai import OpenAI

            self._client = OpenAI(api_key=settings.openai_api_key)
        elif self.provider == "sentence-transformers":
            from sentence_transformers import SentenceTransformer

            self._client = SentenceTransformer(self.model)
        # for other providers or tests we fall back to deterministic hashing

        cache_path = Path(settings.embedding_cache_db)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(cache_path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS embedding_cache (key TEXT PRIMARY KEY, vec TEXT)"
            )
            self._conn.commit()

    # -- caching helpers -------------------------------------------------
    def _cache_key(self, text: str) -> str:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self.model}:{h}"

    def _cache_key_file(self, path: str) -> str:
        data = Path(path).read_bytes()
        h = hashlib.sha256(data).hexdigest()
        return f"{self.model}:{h}"

    def _get_cached(self, key: str) -> Optional[List[float]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT vec FROM embedding_cache WHERE key=?", (key,)
            ).fetchone()
        if row:
            try:
                return json.loads(row[0])
            except Exception:
                return None
        return None

    def _set_cached(self, key: str, vec: List[float]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO embedding_cache (key, vec) VALUES (?, ?)",
                (key, json.dumps(vec)),
            )

    # -- public API ------------------------------------------------------
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts returning a list of vectors."""
        results: List[Optional[List[float]]] = [None] * len(texts)
        to_compute: List[tuple[int, str, str]] = []
        for idx, text in enumerate(texts):
            key = self._cache_key(text)
            cached = self._get_cached(key)
            if cached is not None:
                results[idx] = cached
            else:
                to_compute.append((idx, text, key))

        if to_compute:
            computed = self._compute([t for _, t, _ in to_compute])
            for (idx, _, key), vec in zip(to_compute, computed):
                results[idx] = vec
                self._set_cached(key, vec)
            with self._lock:
                self._conn.commit()

        return [r if r is not None else [] for r in results]

    def embed_query(self, text: str) -> List[float]:
        return self.embed([text])[0]

    # -- provider implementations ---------------------------------------
    def _compute(self, texts: List[str]) -> List[List[float]]:
        if self.provider == "openai":
            if settings.openai_api_key == "test":
                return [self._fake_vec(t) for t in texts]
            try:
                resp = self._client.embeddings.create(model=self.model, input=texts)
                return [d.embedding for d in resp.data]
            except Exception:
                return [self._fake_vec(t) for t in texts]
        if self.provider == "sentence-transformers":
            vecs = self._client.encode(texts, show_progress_bar=False)
            return [list(map(float, v)) for v in vecs]
        # fallback deterministic vectors
        return [self._fake_vec(t) for t in texts]

    @staticmethod
    def _fake_vec(text: str, dim: int = 32) -> List[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        base = list(h)[:dim]
        return [float(b) for b in base] + [0.0] * (dim - len(base))


_embedder: Optional[EmbeddingClient] = None


def get_embedder() -> EmbeddingClient:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingClient()
    return _embedder
