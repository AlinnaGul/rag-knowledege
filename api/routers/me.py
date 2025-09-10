from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_db, get_current_user, get_allowed_collection_ids
from ..services import docs as docs_service

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("/collections", response_model=List[schemas.CollectionRead])
def list_my_collections(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(
            models.Collection,
            func.count(models.DocumentCollection.document_id).label("doc_count"),
        )
        .join(
            models.UserCollection,
            models.UserCollection.collection_id == models.Collection.id,
        )
        .outerjoin(
            models.DocumentCollection,
            models.DocumentCollection.collection_id == models.Collection.id,
        )
        .filter(models.UserCollection.user_id == current_user.id)
        .filter(models.Collection.is_deleted == False)  # noqa: E712
        .group_by(models.Collection.id)
        .order_by(models.Collection.created_at.desc())
        .all()
    )
    collections: List[models.Collection] = []
    for coll, count in rows:
        coll.doc_count = int(count)  # type: ignore[attr-defined]
        collections.append(coll)
    return [schemas.CollectionRead.model_validate(c) for c in collections]


@router.get("/collections/{collection_id}/documents")
def list_my_collection_docs(
    collection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    allowed: List[int] = Depends(get_allowed_collection_ids),
    q: str | None = None,
    page: int = 1,
    size: int = 10,
):
    if collection_id not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return docs_service.list_documents(db, collection_id, q=q, page=page, size=size)
