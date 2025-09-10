import os
import sys
from fastapi.testclient import TestClient


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
    import rag.answerer as answerer  # type: ignore
    import api.services.docs as docs  # type: ignore
    import api.query_logger as qlog  # type: ignore

    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(retriever)
    importlib.reload(answerer)
    importlib.reload(docs)
    importlib.reload(qlog)
    main = importlib.import_module("api.main")  # type: ignore
    importlib.reload(main)
    return main.create_app()


def create_admin(db):
    from api import schemas  # type: ignore
    from api.services import auth as auth_service  # type: ignore

    user_in = schemas.UserCreate(
        email="admin@test.com", name="Admin", password="AdminPass123", role="admin"
    )
    user = auth_service.create_user(db, user_in)
    token = auth_service.issue_access_token(user)
    return user, token


def test_ask_requires_session(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore
    from api.services import docs as docs_service  # type: ignore
    import api.deps as deps  # type: ignore

    app.dependency_overrides[deps.get_allowed_collection_ids] = lambda: [1]
    docs_service.total_embeddings_for_collections = lambda db, ids: 1

    client = TestClient(app)
    db = SessionLocal()
    admin, token = create_admin(db)

    resp = client.post(
        "/api/ask",
        json={"question": "Hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422

