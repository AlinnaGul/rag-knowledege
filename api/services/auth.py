"""
Service functions related to authentication and user management.

These functions encapsulate business logic such as creating users,
authenticating credentials and issuing JWT tokens.
"""
from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from .. import models, schemas
from ..security import verify_password, get_password_hash, create_access_token
from . import email as email_service
import re


def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    """Validate a user's email and password.

    Returns the user object if authentication is successful, otherwise None.
    """
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not user.active or not verify_password(password, user.password_hash):
        return None
    return user


def create_user(db: Session, user_in: schemas.UserCreate) -> models.User:
    """Create a new user with a hashed password.

    Raises HTTPException if the email already exists.
    """
    existing = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    password = user_in.password
    if not _valid_password(password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password does not meet complexity requirements",
        )
    hashed_pw = get_password_hash(password)
    db_user = models.User(
        email=user_in.email,
        name=user_in.name,
        password_hash=hashed_pw,
        role=user_in.role or "user",
        active=user_in.active,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    email_service.send_password_reset(user_in.email, "set-password")
    return db_user


def _valid_password(password: str) -> bool:
    if len(password) < 12:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not (re.search(r"[0-9]", password) or re.search(r"[^A-Za-z0-9]", password)):
        return False
    return True


def issue_access_token(user: models.User) -> str:
    """Create a JWT access token for the given user."""
    payload = {"sub": user.email, "role": user.role}
    return create_access_token(data=payload)