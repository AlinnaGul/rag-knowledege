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
    os.environ["RAW_DOCS_DIR"] = str(tmp_path / "raw")
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


def create_user(db, email, role="user"):
    from api import schemas  # type: ignore
    from api.services import auth as auth_service  # type: ignore

    user_in = schemas.UserCreate(
        email=email, name=email.split("@")[0], password="StrongPass123", role=role
    )
    user = auth_service.create_user(db, user_in)
    token = auth_service.issue_access_token(user)
    return user, token


def test_rbac_isolation(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore
    from api import models  # type: ignore
    from rag.retriever import Retriever  # type: ignore

    client = TestClient(app)
    db = SessionLocal()
    admin, admin_token = create_user(db, "admin@test.com", role="admin")
    user, _ = create_user(db, "user@test.com", role="user")

    # create two collections
    c1 = models.Collection(name="C1", description="", owner_id=admin.id)
    c2 = models.Collection(name="C2", description="", owner_id=admin.id)
    db.add_all([c1, c2])
    db.commit(); db.refresh(c1); db.refresh(c2)

    # upload distinct docs with shared term "common"
    resp = client.post(
        f"/api/admin/collections/{c1.id}/documents",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("a.txt", b"alpha common", "text/plain")},
    )
    doc1 = resp.json()["uploads"][0]["document_id"]
    meta1 = tmp_path / "collections" / str(c1.id) / f"{doc1}.json"
    assert meta1.exists()
    resp = client.post(
        f"/api/admin/collections/{c2.id}/documents",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("b.txt", b"beta common", "text/plain")},
    )
    doc2 = resp.json()["uploads"][0]["document_id"]
    meta2 = tmp_path / "collections" / str(c2.id) / f"{doc2}.json"
    assert meta2.exists()

    # assign user only to first collection
    resp = client.put(
        f"/api/admin/users/{user.id}/collections",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"assigned": [c1.id]},
    )
    assert resp.status_code == 204

    retriever = Retriever()
    res = retriever.search("common", allowed_collections=[c1.id])
    cited = {r["metadata"].get("doc_id") for r in res}
    assert cited == {doc1}
    assert all(r["metadata"].get("collection_id") == c1.id for r in res)

    res2 = retriever.search("common", allowed_collections=[c2.id])
    cited2 = {r["metadata"].get("doc_id") for r in res2}
    assert cited2 == {doc2}
    assert all(r["metadata"].get("collection_id") == c2.id for r in res2)
