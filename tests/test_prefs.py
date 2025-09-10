import os
import sys
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


def create_user(db, email="user@test.com", role="user"):
    from api import schemas  # type: ignore
    from api.services import auth as auth_service  # type: ignore

    user_in = schemas.UserCreate(email=email, name="User", password="ValidPass123", role=role)
    user = auth_service.create_user(db, user_in)
    token = auth_service.issue_access_token(user)
    return token


def test_prefs_clamp(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore

    client = TestClient(app)
    db = SessionLocal()
    token = create_user(db, role="admin")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/me/prefs", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["top_k"] == 6

    resp = client.patch(
        "/api/me/prefs",
        json={"temperature": 5, "top_k": 100},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["temperature"] == 2.0
    assert body["top_k"] == 20
