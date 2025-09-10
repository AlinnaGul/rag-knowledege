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


def test_chat_rbac(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore
    from api.services import rag as rag_service  # type: ignore

    client = TestClient(app)
    db = SessionLocal()
    admin, admin_token = create_admin(db)
    user, user_token = create_user(db)

    def fake_ask_question(**kwargs):
        return {"answer": "hello", "citations": [], "followups": [], "query_id": 1}
    orig_ask = rag_service.ask_question
    rag_service.ask_question = fake_ask_question

    # Create collection
    resp = client.post(
        "/api/admin/collections",
        json={"name": "C1"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    cid = resp.json()["id"]

    session = client.post(
        "/api/chat/sessions",
        headers={"Authorization": f"Bearer {user_token}"},
    ).json()["id"]
    # User without collections -> Access Denied
    resp = client.post(
        "/api/chat/messages",
        json={"question": "hello", "session_id": session},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200
    assert "Access Denied" in resp.text

    # Assign collection to user
    resp = client.put(
        f"/api/admin/users/{user.id}/collections",
        json={"assigned": [cid]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204

    # upload doc so collection has content
    from pypdf import PdfWriter
    import io

    writer = PdfWriter(); writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO(); writer.write(buf); data = buf.getvalue()
    client.post(
        f"/api/admin/collections/{cid}/documents",
        headers={"Authorization": f"Bearer {admin_token}"},
        files={"file": ("a.pdf", data, "application/pdf")},
    )

    resp = client.post(
        "/api/chat/messages",
        json={"question": "hello", "session_id": session},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200
    assert str(cid) in resp.text

    # Remove assignment -> Access Denied again
    resp = client.put(
        f"/api/admin/users/{user.id}/collections",
        json={"assigned": []},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204

    resp = client.post(
        "/api/chat/messages",
        json={"question": "hello", "session_id": session},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200
    assert "Access Denied" in resp.text
    rag_service.ask_question = orig_ask
