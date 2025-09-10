"""
User memory service.

This module provides simple helpers to persist and retrieve user memories.  A
memory consists of a key (e.g. a fact identifier or question) and a value
(e.g. the extracted fact or preference).  When users ask questions the RAG
pipeline can consult these memories to enrich the context with prior
knowledge.
"""
from __future__ import annotations

from typing import List, Dict
from sqlalchemy.orm import Session

from .. import models


def save_memory(db: Session, user_id: int, key: str, value: str) -> None:
    """Insert or update a memory entry for a user.

    If an entry with the same (user_id, key) exists, its value and timestamp
    are updated.  Otherwise a new row is created.
    """
    row = (
        db.query(models.UserMemory)
        .filter(models.UserMemory.user_id == user_id, models.UserMemory.key == key)
        .first()
    )
    if row:
        row.value = value
    else:
        row = models.UserMemory(user_id=user_id, key=key, value=value)
        db.add(row)
    db.commit()


def load_memories(db: Session, user_id: int) -> List[Dict[str, str]]:
    """Return all memories for a user as a list of dicts with text and metadata."""
    rows = (
        db.query(models.UserMemory)
        .filter(models.UserMemory.user_id == user_id)
        .order_by(models.UserMemory.updated_at.desc())
        .all()
    )
    results: List[Dict[str, str]] = []
    for row in rows:
        results.append(
            {
                "text": row.value,
                "metadata": {"title": "Memory", "page": 0, "doc_id": 0, "collection_id": -1, "collection_name": "memory", "chunk_id": f"mem:{row.id}"},
                "score": 1.0,
            }
        )
    return results