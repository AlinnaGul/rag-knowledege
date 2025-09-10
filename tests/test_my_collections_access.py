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
    import api.services.docs as docs  # type: ignore
    import api.query_logger as qlog  # type: ignore

    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(retriever)
    importlib.reload(docs)
    importlib.reload(qlog)

    main = importlib.import_module("api.main")  # type: ignore
    importlib.reload(main)
    return main.create_app()


def create_admin(db):
    from api import schemas  # type: ignore
    from api.services import auth as auth_service  # type: ignore

    user_in = schemas.UserCreate(email="admin@test.com", name="Admin", password="AdminPass123", role="admin")
    user = auth_service.create_user(db, user_in)
    token = auth_service.issue_access_token(user)
    return user, token


def create_user(db):
    from api import schemas  # type: ignore
    from api.services import auth as auth_service  # type: ignore

    user_in = schemas.UserCreate(email="user@test.com", name="User", password="ValidPass123", role="user")
    user = auth_service.create_user(db, user_in)
    token = auth_service.issue_access_token(user)
    return user, token


def test_collections_access(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore

    client = TestClient(app)
    db = SessionLocal()
    admin, admin_token = create_admin(db)
    user, user_token = create_user(db)
    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    headers_user = {"Authorization": f"Bearer {user_token}"}

    # create two collections
    cid1 = client.post("/api/admin/collections", json={"name": "C1"}, headers=headers_admin).json()["id"]
    cid2 = client.post("/api/admin/collections", json={"name": "C2"}, headers=headers_admin).json()["id"]

    # assign first collection to user
    resp = client.put(
        f"/api/admin/users/{user.id}/collections",
        json={"assigned": [cid1]},
        headers=headers_admin,
    )
    assert resp.status_code == 204

    # user sees only assigned collection
    resp = client.get("/api/me/collections", headers=headers_user)
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert ids == [cid1]

    # admin sees all collections
    resp = client.get("/api/admin/collections", headers=headers_admin)
    assert resp.status_code == 200
    ids = {c["id"] for c in resp.json()}
    assert ids == {cid1, cid2}

    # user cannot access admin endpoint
    resp = client.get("/api/admin/collections", headers=headers_user)
    assert resp.status_code == 403
