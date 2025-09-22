"""
Embedding backend abstraction with caching and **hybrid (semantic + symbolic)** enrichment.

Modular components:
- EntityExtractor: pluggable entity detection
- KnowledgeGraph: fetch related triples for detected entities
- Cache: SQLite-backed vector cache keyed by model + input hash
- Providers: EmbeddingProvider protocol + OpenAI/SentenceTransformers/Fake implementations
- HybridEmbedder: orchestrates symbolic enrichment + provider + cache

Public API:
- get_embedder() -> HybridEmbedder (drop-in replacement)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple
from pathlib import Path
import hashlib
import json
import re
import sqlite3
import threading

from api.config import settings

# --------------------------------------------------------------------------------------
# Entity extraction
# --------------------------------------------------------------------------------------

class EntityExtractor(Protocol):
    def extract(self, text: str) -> List[str]: ...


class RegexEntityExtractor:
    """Very lightweight capitalized-token extractor (replace with spaCy/etc. if desired)."""
    _PATTERN = re.compile(r"\b[A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*\b")

    def extract(self, text: str) -> List[str]:
        ents = self._PATTERN.findall(text or "")
        # de-duplicate while preserving order
        seen, out = set(), []
        for e in ents:
            if e not in seen:
                seen.add(e)
                out.append(e)
        return out


# --------------------------------------------------------------------------------------
# Knowledge Graph
# --------------------------------------------------------------------------------------

class KnowledgeGraph(Protocol):
    def fetch_related_triples(self, entity: str) -> List[str]: ...


class InMemoryKG:
    """Simple in-memory KG with a tiny demo corpus.
    Replace with your real KG adapter (Neo4j, RDF store, etc.).
    """
    def __init__(self):
        # subject -> list[(predicate, object)]
        self.triples: Dict[str, List[Tuple[str, str]]] = {
            "Python": [("is_a", "Programming Language"), ("used_for", "AI")],
            "OpenAI": [("developed", "GPT"), ("field", "AI Research")],
        }

    def fetch_related_triples(self, entity: str) -> List[str]:
        rows = self.triples.get(entity, [])
        return [f"{entity} {pred} {obj}" for pred, obj in rows]


# --------------------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------------------

class VectorCache:
    def get(self, key: str) -> Optional[List[float]]: ...
    def set(self, key: str, vec: List[float]) -> None: ...


class SQLiteCache(VectorCache):
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS embedding_cache (key TEXT PRIMARY KEY, vec TEXT)"
            )
            self._conn.commit()

    def get(self, key: str) -> Optional[List[float]]:
        with self._lock:
            row = self._conn.execute("SELECT vec FROM embedding_cache WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def set(self, key: str, vec: List[float]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO embedding_cache (key, vec) VALUES (?, ?)",
                (key, json.dumps(vec)),
            )
            self._conn.commit()


# --------------------------------------------------------------------------------------
# Embedding providers
# --------------------------------------------------------------------------------------

class EmbeddingProvider(Protocol):
    model: str
    def embed(self, texts: Sequence[str]) -> List[List[float]]: ...


class OpenAIProvider:
    def __init__(self, model: str, api_key: Optional[str]):
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("openai package not available") from e
        self._client = OpenAI(api_key=api_key)
        self.model = model

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        try:
            resp = self._client.embeddings.create(model=self.model, input=list(texts))
            return [list(d.embedding) for d in resp.data]
        except Exception:  # pragma: no cover
            return [FakeProvider._fake_vec(t) for t in texts]


class SentenceTransformersProvider:
    def __init__(self, model: str):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("sentence-transformers not available") from e
        self._st = SentenceTransformer(model)
        self.model = model

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        vecs = self._st.encode(list(texts), show_progress_bar=False)
        return [list(map(float, v)) for v in vecs]


class FakeProvider:
    """Deterministic fallback, useful for tests and offline mode."""
    def __init__(self, model: str = "fake-emb-32"):
        self.model = model

    @staticmethod
    def _fake_vec(text: str, dim: int = 32) -> List[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        base = list(h)[:dim]
        return [float(b) for b in base] + [0.0] * max(0, dim - len(base))

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._fake_vec(t) for t in texts]


# --------------------------------------------------------------------------------------
# Hybrid embedder (semantic + symbolic)
# --------------------------------------------------------------------------------------

@dataclass
class HybridEmbedder:
    provider: EmbeddingProvider
    cache: VectorCache
    entity_extractor: EntityExtractor
    kg: KnowledgeGraph

    def _cache_key(self, text: str) -> str:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self.provider.model}:{h}"

    def _enrich(self, text: str) -> str:
        """Append related KG triples to the text if entities are detected."""
        entities = self.entity_extractor.extract(text)
        if not entities:
            return text
        triples: List[str] = []
        for e in entities:
            triples.extend(self.kg.fetch_related_triples(e))
        if not triples:
            return text
        # Keep enrichment small to avoid prompt/embedding blow-up
        joined = " ".join(triples[:8])
        return f"{text} {joined}"

    # Public API
    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        enriched: List[str] = [self._enrich(t) for t in texts]
        out: List[Optional[List[float]]] = [None] * len(enriched)
        to_compute: List[Tuple[int, str, str]] = []  # (idx, enriched_text, key)
        for i, t in enumerate(enriched):
            key = self._cache_key(t)
            cached = self.cache.get(key)
            if cached is not None:
                out[i] = cached
            else:
                to_compute.append((i, t, key))
        if to_compute:
            vecs = self.provider.embed([t for _, t, _ in to_compute])
            for (idx, _t, key), vec in zip(to_compute, vecs):
                out[idx] = vec
                self.cache.set(key, vec)
        # all filled
        return [v if v is not None else [] for v in out]

    def embed_query(self, text: str) -> List[float]:
        return self.embed([text])[0]


# --------------------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------------------

_embedder: Optional[HybridEmbedder] = None


def _make_provider() -> EmbeddingProvider:
    provider = (getattr(settings, "embedding_provider", "").lower() or "openai")
    model = getattr(settings, "embedding_model", "text-embedding-3-small")
    if provider == "openai":
        return OpenAIProvider(model=model, api_key=getattr(settings, "openai_api_key", None))
    if provider in {"sentence-transformers", "sentence_transformers", "st"}:
        return SentenceTransformersProvider(model=model)
    return FakeProvider(model=model)


def get_embedder() -> HybridEmbedder:
    global _embedder
    if _embedder is None:
        cache_path = Path(getattr(settings, "embedding_cache_db", "./.cache/embeddings.sqlite3"))
        cache = SQLiteCache(cache_path)
        provider = _make_provider()
        extractor = RegexEntityExtractor()
        kg = InMemoryKG()
        _embedder = HybridEmbedder(provider=provider, cache=cache, entity_extractor=extractor, kg=kg)
    return _embedder
