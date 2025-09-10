"""Service functions for managing collections."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..storage import StorageAdapter


def create_collection(
    db: Session,
    owner: models.User,
    collection_in: schemas.CollectionCreate,
    storage: StorageAdapter,
) -> models.Collection:
    existing = (
        db.query(models.Collection)
        .filter(
            models.Collection.owner_id == owner.id,
            models.Collection.name == collection_in.name,
            models.Collection.is_deleted.is_(False),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Collection name already exists",
        )
    collection = models.Collection(
        name=collection_in.name,
        description=collection_in.description,
        owner_id=owner.id,
        visibility=collection_in.visibility,
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    storage.create_collection(collection.id)
    collection.doc_count = 0  # type: ignore[attr-defined]
    return collection


def list_collections(db: Session, owner: models.User) -> list[models.Collection]:
    rows = (
        db.query(
            models.Collection,
            func.count(models.DocumentCollection.document_id).label("doc_count"),
        )
        .outerjoin(
            models.DocumentCollection,
            models.DocumentCollection.collection_id == models.Collection.id,
        )
        .filter(
            models.Collection.owner_id == owner.id,
            models.Collection.is_deleted.is_(False),
        )
        .group_by(models.Collection.id)
        .order_by(models.Collection.created_at.desc())
        .all()
    )
    collections: list[models.Collection] = []
    for coll, count in rows:
        coll.doc_count = int(count)  # type: ignore[attr-defined]
        collections.append(coll)
    return collections


def update_collection(
    db: Session,
    collection: models.Collection,
    update_in: schemas.CollectionUpdate,
) -> models.Collection:
    if update_in.name and update_in.name != collection.name:
        existing = (
            db.query(models.Collection)
            .filter(
                models.Collection.owner_id == collection.owner_id,
                models.Collection.name == update_in.name,
                models.Collection.is_deleted.is_(False),
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Collection name already exists",
            )
        collection.name = update_in.name
    if update_in.description is not None:
        collection.description = update_in.description
    if update_in.visibility is not None:
        collection.visibility = update_in.visibility
    collection.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(collection)

    # Update collection name in existing embeddings
    from rag.retriever import get_collection_client

    try:
        client = get_collection_client(collection.id)
        chroma = client.get_or_create_collection(name="docs")
        res = chroma.get(
            where={"collection_id": collection.id},
            include=["ids", "metadatas"],
        )
        ids = res.get("ids", [])
        metas = res.get("metadatas", [])
        if ids and metas:
            updated = []
            for m in metas:
                m = m or {}
                m["collection_name"] = collection.name
                updated.append(m)
            chroma.update(ids=ids, metadatas=updated)
    except Exception:
        pass
    count = (
        db.query(func.count(models.DocumentCollection.document_id))
        .filter(models.DocumentCollection.collection_id == collection.id)
        .scalar()
    )
    collection.doc_count = int(count or 0)  # type: ignore[attr-defined]
    return collection


def delete_collection(
    db: Session,
    collection: models.Collection,
    storage: StorageAdapter,
) -> None:
    collection.is_deleted = True
    collection.updated_at = datetime.now(timezone.utc)
    db.commit()
    storage.delete_collection(collection.id)
