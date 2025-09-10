"""User preferences endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import get_db, get_current_user
from ..schemas import UserPrefsRead, UserPrefsUpdate
from ..services import prefs as prefs_service
from .. import models

router = APIRouter(prefix="/api/me/prefs", tags=["prefs"])


@router.get("", response_model=UserPrefsRead)
def read_prefs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    prefs = prefs_service.get_prefs(db, current_user.id)
    return UserPrefsRead(
        temperature=prefs.temperature,
        top_k=prefs.top_k,
        mmr_lambda=prefs.mmr_lambda,
        theme=prefs.theme,
    )


@router.patch("", response_model=UserPrefsRead)
def update_prefs(
    req: UserPrefsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role in ("admin", "superadmin"):
        prefs = prefs_service.update_prefs(
            db,
            current_user.id,
            temperature=req.temperature,
            top_k=req.top_k,
            mmr_lambda=req.mmr_lambda,
            theme=req.theme,
        )
    else:
        prefs = prefs_service.update_prefs(
            db,
            current_user.id,
            theme=req.theme,
        )
    return UserPrefsRead(
        temperature=prefs.temperature,
        top_k=prefs.top_k,
        mmr_lambda=prefs.mmr_lambda,
        theme=prefs.theme,
    )
