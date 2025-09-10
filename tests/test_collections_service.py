import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure project root in path
current_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("JWT_SECRET", "secret")

from api import models, schemas  # type: ignore  # noqa: E402
from api.services import collections as collections_service  # type: ignore  # noqa: E402
from api.storage import LocalStorageAdapter  # type: ignore  # noqa: E402
from fastapi import HTTPException  # type: ignore  # noqa: E402


def setup_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    user = models.User(email="admin@example.com", name="Admin", password_hash="hash", role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    return db, user


def test_service_crud(tmp_path):
    db, user = setup_db()
    storage = LocalStorageAdapter(str(tmp_path))
    coll_in = schemas.CollectionCreate(name="A", description="d")
    coll = collections_service.create_collection(db, user, coll_in, storage)
    assert (tmp_path / str(coll.id)).exists()

    coll = collections_service.update_collection(db, coll, schemas.CollectionUpdate(name="B"))
    assert coll.name == "B"

    collections_service.delete_collection(db, coll, storage)
    assert coll.is_deleted is True
    assert not (tmp_path / str(coll.id)).exists()

    coll2 = collections_service.create_collection(db, user, coll_in, storage)
    assert coll2.name == "A"
    with pytest.raises(HTTPException):
        collections_service.create_collection(db, user, coll_in, storage)
