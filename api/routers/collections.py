"""Collection management endpoints."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_db, require_role
from ..services import collections as service
from ..storage import LocalStorageAdapter
from ..config import settings

router = APIRouter(prefix="/api/admin/collections", tags=["collections"])


@router.post("", response_model=schemas.CollectionRead, status_code=status.HTTP_201_CREATED)
def create_collection(
    collection_in: schemas.CollectionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    storage = LocalStorageAdapter(settings.collections_dir)
    return service.create_collection(db, current_user, collection_in, storage)


@router.get("", response_model=List[schemas.CollectionRead])
def list_collections(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    return service.list_collections(db, current_user)


@router.patch("/{collection_id}", response_model=schemas.CollectionRead)
def rename_collection(
    collection_id: int,
    update_in: schemas.CollectionUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    collection = (
        db.query(models.Collection)
        .filter(models.Collection.id == collection_id, models.Collection.owner_id == current_user.id)
        .first()
    )
    if not collection or collection.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return service.update_collection(db, collection, update_in)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    collection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    collection = (
        db.query(models.Collection)
        .filter(models.Collection.id == collection_id, models.Collection.owner_id == current_user.id)
        .first()
    )
    if not collection or collection.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    storage = LocalStorageAdapter(settings.collections_dir)
    service.delete_collection(db, collection, storage)
    return None
