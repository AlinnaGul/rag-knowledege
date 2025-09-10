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


def create_admin(db):
    from api import schemas  # type: ignore
    from api.services import auth as auth_service  # type: ignore

    user_in = schemas.UserCreate(
        email="admin@test.com", name="Admin", password="AdminPass123", role="admin"
    )
    user = auth_service.create_user(db, user_in)
    token = auth_service.issue_access_token(user)
    return user, token


def create_user(db):
    from api import schemas  # type: ignore
    from api.services import auth as auth_service  # type: ignore

    user_in = schemas.UserCreate(
        email="user@test.com", name="User", password="ValidPass123", role="user"
    )
    user = auth_service.create_user(db, user_in)
    token = auth_service.issue_access_token(user)
    return user, token


def test_ask_respects_user_collections(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore
    from api.services import rag as rag_service  # type: ignore

    client = TestClient(app)
    db = SessionLocal()
    admin, admin_token = create_admin(db)
    user, user_token = create_user(db)

    # Patch LLM-dependent functions
    orig_rewrite = rag_service.rewrite_question
    orig_generate = rag_service.generate_answer

    def fake_generate(question, contexts, temperature=None, history=None):
        citations = []
        for c in contexts:
            meta = c.get("metadata", {})
            citations.append(
                {
                    "id": meta.get("chunk_id", "0"),
                    "filename": meta.get("title", "Document"),
                    "page": meta.get("page", 0),
                    "score": c.get("score", 0.0),
                    "collection_id": meta.get("collection_id", 0),
                    "collection_name": meta.get("collection_name", ""),
                    "snippet": c.get("text", ""),
                    "url": None,
                    "section": None,
                }
            )
        return {"answer": "ok", "citations": citations, "latency_ms": 0, "followups": []}

    rag_service.rewrite_question = lambda q: q
    rag_service.generate_answer = fake_generate

    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    headers_user = {"Authorization": f"Bearer {user_token}"}

    # Create two collections
    cid1 = client.post(
        "/api/admin/collections", json={"name": "C1"}, headers=headers_admin
    ).json()["id"]
    cid2 = client.post(
        "/api/admin/collections", json={"name": "C2"}, headers=headers_admin
    ).json()["id"]

    # Upload distinct documents
    client.post(
        f"/api/admin/collections/{cid1}/documents",
        headers=headers_admin,
        files={"file": ("a.txt", b"apple", "text/plain")},
    )
    client.post(
        f"/api/admin/collections/{cid2}/documents",
        headers=headers_admin,
        files={"file": ("b.txt", b"banana", "text/plain")},
    )

    # Create chat session
    sess = client.post("/api/chat/sessions", headers=headers_user).json()["id"]

    # Without assignments -> 403
    resp = client.post(
        "/api/ask",
        json={"question": "apple", "session_id": sess},
        headers=headers_user,
    )
    assert resp.status_code == 403

    # Assign first collection to user
    client.put(
        f"/api/admin/users/{user.id}/collections",
        json={"assigned": [cid1]},
        headers=headers_admin,
    )

    # Ask about document in allowed collection
    resp = client.post(
        "/api/ask",
        json={"question": "apple", "session_id": sess},
        headers=headers_user,
    )
    assert resp.status_code == 200
    cids = {c["collection_id"] for c in resp.json()["citations"]}
    assert cids == {cid1}

    # Removing assignments blocks access again
    client.put(
        f"/api/admin/users/{user.id}/collections",
        json={"assigned": []},
        headers=headers_admin,
    )
    resp = client.post(
        "/api/ask",
        json={"question": "apple", "session_id": sess},
        headers=headers_user,
    )
    assert resp.status_code == 403

    rag_service.rewrite_question = orig_rewrite
    rag_service.generate_answer = orig_generate

