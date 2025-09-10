"""
FastAPI dependency functions for common operations.

Includes dependencies to get a database session, the current authenticated user
and role-based access control checks.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from . import models
from .db import get_db
from .security import oauth2_scheme, decode_access_token


def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> models.User:
    """Retrieve the currently authenticated user based on the JWT access token."""
    token_data = decode_access_token(token)
    user = db.query(models.User).filter(models.User.email == token_data.email).first()
    if user is None or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive or invalid user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(role: str):
    """Create a dependency that ensures the current user has the given role.

    Roles are hierarchical: superadmin > admin > user.  Requesting the "admin"
    role allows both admins and superadmins, while "superadmin" requires an
    exact match.
    """

    def role_dependency(current_user: models.User = Depends(get_current_user)) -> models.User:
        allowed = {role}
        if role == "admin":
            allowed.add("superadmin")
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient privileges",
            )
        return current_user

    return role_dependency


def get_allowed_collection_ids(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> List[int]:
    """Return collection IDs the user is allowed to access.

    Admins are granted access to all non-deleted collections by default.
    """
    if current_user.role in ("admin", "superadmin"):
        rows = (
            db.query(models.Collection.id)
            .filter(models.Collection.is_deleted == False)  # noqa: E712
            .all()
        )
        return [r[0] for r in rows]

    rows = (
        db.query(models.UserCollection.collection_id)
        .join(
            models.Collection,
            models.Collection.id == models.UserCollection.collection_id,
        )
        .filter(models.UserCollection.user_id == current_user.id)
        .filter(models.Collection.is_deleted == False)  # noqa: E712
        .all()
    )
    return [r[0] for r in rows]
