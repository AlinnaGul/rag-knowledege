"""
User management endpoints.

Admins can create new users and modify existing ones (e.g. disable accounts or
reset passwords).  The endpoints are protected by the admin role.
"""
from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..schemas import (
    UserCreate,
    UserRead,
    UserUpdate,
    UserRoleUpdate,
    CollectionAssignment,
    UserPrefsRead,
    UserPrefsUpdate,
)
from ..deps import get_db, require_role
from ..services import auth as auth_service
from ..services import prefs as prefs_service
from .. import models


router = APIRouter(prefix="/api/admin/users", tags=["users"])


@router.get("", response_model=List[UserRead])
def list_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    """List all users with collection counts (admin only)."""
    rows = (
        db.query(
            models.User,
            func.count(models.UserCollection.collection_id).label("collection_count"),
        )
        .outerjoin(
            models.UserCollection,
            models.User.id == models.UserCollection.user_id,
        )
        .group_by(models.User.id)
        .order_by(models.User.id)
        .all()
    )
    return [
        UserRead.model_validate(user).model_copy(update={"collection_count": count})
        for user, count in rows
    ]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    """Create a new user (admin only)."""
    if current_user.role != "superadmin" and user_in.role == "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create superadmin")
    user = auth_service.create_user(db, user_in)
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    """Update a user's attributes (admin only; excludes role changes)."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user_in.name is not None:
        user.name = user_in.name

    if user_in.email is not None and user_in.email != user.email:
        exists = db.query(models.User).filter(models.User.email == user_in.email).first()
        if exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        user.email = user_in.email

    if user_in.active is not None and user_in.active != user.active:
        if user.role == "admin" and not user_in.active:
            admin_count = (
                db.query(models.User)
                .filter(models.User.role.in_(["admin", "superadmin"]), models.User.active == True)
                .count()
            )
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="At least one admin is required",
                )
        if user.role == "superadmin" and not user_in.active:
            super_count = (
                db.query(models.User)
                .filter(models.User.role == "superadmin", models.User.active == True)
                .count()
            )
            if super_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="At least one superadmin is required",
                )
        user.active = user_in.active

    if user_in.password:
        if not auth_service._valid_password(user_in.password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password does not meet complexity requirements",
            )
        user.password_hash = auth_service.get_password_hash(user_in.password)

    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/role", response_model=UserRead)
def update_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("superadmin")),
):
    """Update a user's role (superadmin only)."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.role == "superadmin" and payload.role != "superadmin":
        super_count = db.query(models.User).filter(models.User.role == "superadmin", models.User.active == True).count()
        if super_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one superadmin is required",
            )
    if user.role == "admin" and payload.role != "admin":
        admin_count = db.query(models.User).filter(models.User.role.in_(["admin", "superadmin"]), models.User.active == True).count()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one admin is required",
            )

    user.role = payload.role
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}/collections", response_model=CollectionAssignment)
def get_user_collections(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    rows = (
        db.query(models.UserCollection.collection_id)
        .filter(models.UserCollection.user_id == user_id)
        .all()
    )
    return {"assigned": [r[0] for r in rows]}


@router.put("/{user_id}/collections", status_code=status.HTTP_204_NO_CONTENT)
def set_user_collections(
    user_id: int,
    assignment: CollectionAssignment,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    db.query(models.UserCollection).filter(
        models.UserCollection.user_id == user_id
    ).delete(synchronize_session=False)
    if assignment.assigned:
        db.add_all(
            [models.UserCollection(user_id=user_id, collection_id=cid) for cid in assignment.assigned]
        )
    db.commit()
    return None


@router.get("/{user_id}/prefs", response_model=UserPrefsRead)
def get_user_prefs(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    prefs = prefs_service.get_prefs(db, user_id)
    return UserPrefsRead(
        temperature=prefs.temperature,
        top_k=prefs.top_k,
        mmr_lambda=prefs.mmr_lambda,
        theme=prefs.theme,
    )


@router.patch("/{user_id}/prefs", response_model=UserPrefsRead)
def update_user_prefs(
    user_id: int,
    req: UserPrefsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    prefs = prefs_service.update_prefs(
        db,
        user_id,
        temperature=req.temperature,
        top_k=req.top_k,
        mmr_lambda=req.mmr_lambda,
        theme=req.theme,
    )
    return UserPrefsRead(
        temperature=prefs.temperature,
        top_k=prefs.top_k,
        mmr_lambda=prefs.mmr_lambda,
        theme=prefs.theme,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete self")
    user = db.query(models.User).filter(models.User.id == user_id, models.User.active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role == "admin":
        admin_count = db.query(models.User).filter(models.User.role.in_(["admin", "superadmin"]), models.User.active == True).count()
        if admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one admin is required")
    if user.role == "superadmin":
        super_count = db.query(models.User).filter(models.User.role == "superadmin", models.User.active == True).count()
        if super_count <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one superadmin is required")
    user.active = False
    db.commit()
    return None
