from __future__ import annotations

"""Service functions for user preference management."""

from sqlalchemy.orm import Session

from .. import models


def get_prefs(db: Session, user_id: int) -> models.UserPrefs:
    prefs = db.query(models.UserPrefs).filter(models.UserPrefs.user_id == user_id).first()
    if not prefs:
        prefs = models.UserPrefs(user_id=user_id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


def update_prefs(
    db: Session,
    user_id: int,
    temperature: float | None = None,
    top_k: int | None = None,
    mmr_lambda: float | None = None,
    theme: str | None = None,
) -> models.UserPrefs:
    prefs = get_prefs(db, user_id)
    if temperature is not None:
        prefs.temperature = max(0.0, min(2.0, float(temperature)))
    if top_k is not None:
        prefs.top_k = max(1, min(20, int(top_k)))
    if mmr_lambda is not None:
        prefs.mmr_lambda = max(0.0, min(1.0, float(mmr_lambda)))
    if theme is not None:
        prefs.theme = theme
    db.commit()
    db.refresh(prefs)
    return prefs
