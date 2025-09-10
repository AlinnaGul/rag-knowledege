import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

# Ensure project root in path
current_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def create_app(tmp_path):
    os.environ.setdefault("OPENAI_API_KEY", "test")
    os.environ.setdefault("JWT_SECRET", "secret")
    os.environ["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path/'app.db'}"
    os.environ["COLLECTIONS_DIR"] = str(tmp_path / "collections")
    os.environ["CHROMA_PERSIST_DIR"] = str(tmp_path / "chroma")
    os.environ["LOGS_DIR"] = str(tmp_path / "logs")
    import importlib
    import api.config as config  # type: ignore
    import api.db as db  # type: ignore
    import rag.retriever as retriever  # type: ignore
    import api.services.docs as docs  # type: ignore
    import api.query_logger as qlog  # type: ignore

    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(retriever)
    importlib.reload(docs)
    importlib.reload(qlog)

    main = importlib.import_module("api.main")  # type: ignore
    importlib.reload(main)
    app = main.create_app()
    return app


def create_admin(db):
    from api import schemas, models  # type: ignore
    from api.services import auth as auth_service  # type: ignore

    user_in = schemas.UserCreate(email="admin@test.com", name="Admin", password="AdminPass123", role="admin")
    user = auth_service.create_user(db, user_in)
    token = auth_service.issue_access_token(user)
    return token


def test_collection_flow(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore

    client = TestClient(app)
    db = SessionLocal()
    token = create_admin(db)
    headers = {"Authorization": f"Bearer {token}"}

    # Create
    resp = client.post(
        "/api/admin/collections",
        json={"name": "C1", "description": "d"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["doc_count"] == 0
    cid = data["id"]

    # Rename
    resp = client.patch(
        f"/api/admin/collections/{cid}",
        json={"name": "C2"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "C2"
    assert data["doc_count"] == 0

    # Delete
    resp = client.delete(f"/api/admin/collections/{cid}", headers=headers)
    assert resp.status_code == 204

    # Ensure list empty
    resp = client.get("/api/admin/collections", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []
