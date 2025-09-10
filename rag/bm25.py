from __future__ import annotations

"""BM25 indexing and search utilities using Whoosh."""

from pathlib import Path
from typing import List, Dict, Any
import json

from whoosh import index
from whoosh.fields import Schema, ID, TEXT, STORED, NUMERIC
from whoosh.qparser import QueryParser

from api.config import settings


_schema = Schema(
    chunk_id=ID(stored=True, unique=True),
    document_id=NUMERIC(stored=True, numtype=int),
    text=TEXT(stored=True),
    meta=STORED,
)


def _base_dir() -> Path:
    return Path(getattr(settings, "bm25_index_dir", "./data/bm25"))


def _index_path(collection_id: int) -> Path:
    return _base_dir() / f"coll_{collection_id}"


def get_or_create_index(collection_id: int):
    path = _index_path(collection_id)
    path.mkdir(parents=True, exist_ok=True)
    if index.exists_in(str(path)):
        return index.open_dir(str(path))
    return index.create_in(str(path), _schema)


def index_chunks(collection_id: int, doc_id: int, ids: List[str], texts: List[str], metadatas: List[Dict[str, Any]]) -> None:
    """Index document chunks for BM25 search."""
    ix = get_or_create_index(collection_id)
    writer = ix.writer()
    # Remove any prior entries for this document
    writer.delete_by_term("document_id", doc_id)
    for cid, text, meta in zip(ids, texts, metadatas):
        writer.add_document(
            chunk_id=str(cid),
            document_id=int(doc_id),
            text=text,
            meta=json.dumps(meta),
        )
    writer.commit()


def search(collection_id: int, query: str, n_results: int) -> List[Dict[str, Any]]:
    ix = get_or_create_index(collection_id)
    qp = QueryParser("text", schema=ix.schema)
    q = qp.parse(query)
    with ix.searcher() as searcher:
        results = searcher.search(q, limit=n_results)
        out: List[Dict[str, Any]] = []
        for hit in results:
            meta = json.loads(hit["meta"]) if hit.get("meta") else {}
            out.append(
                {
                    "id": hit["chunk_id"],
                    "text": hit["text"],
                    "metadata": meta,
                    "score": float(hit.score),
                }
            )
    return out
