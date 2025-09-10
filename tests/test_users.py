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


def create_superadmin(db):
    from api import schemas, models  # type: ignore
    from api.services import auth as auth_service  # type: ignore

    user_in = schemas.UserCreate(email="admin@test.com", name="Super", password="AdminPass123", role="superadmin")
    user = auth_service.create_user(db, user_in)
    token = auth_service.issue_access_token(user)
    return token


def test_user_management(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore
    from api.services import email as email_service  # type: ignore

    email_service.sent_emails.clear()

    client = TestClient(app)
    db = SessionLocal()
    token = create_superadmin(db)
    headers = {"Authorization": f"Bearer {token}"}
    from api import models  # type: ignore
    admin_id = db.query(models.User).filter(models.User.email == "admin@test.com").first().id

    # Weak password rejected
    resp = client.post(
        "/api/admin/users",
        json={"email": "weak@test.com", "name": "Weak", "role": "user", "password": "short"},
        headers=headers,
    )
    assert resp.status_code == 422

    # Create user with strong password
    resp = client.post(
        "/api/admin/users",
        json={"email": "user@test.com", "name": "User", "role": "user", "password": "ValidPass123"},
        headers=headers,
    )
    assert resp.status_code == 201
    uid = resp.json()["id"]
    assert any(e["email"] == "user@test.com" for e in email_service.sent_emails)

    # Duplicate email
    resp = client.post(
        "/api/admin/users",
        json={"email": "user@test.com", "name": "User", "role": "user", "password": "ValidPass123"},
        headers=headers,
    )
    assert resp.status_code == 400

    # Invalid email
    resp = client.post(
        "/api/admin/users",
        json={"email": "bad", "name": "User", "role": "user", "password": "ValidPass123"},
        headers=headers,
    )
    assert resp.status_code == 422

    # Login with new user (non-admin)
    resp = client.post("/api/auth/login", json={"email": "user@test.com", "password": "ValidPass123"})
    assert resp.status_code == 200
    user_token = resp.json()["token"]

    # Non-admin role check
    resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == 403

    # Cannot demote last superadmin
    resp = client.patch(
        f"/api/admin/users/{admin_id}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert resp.status_code == 400

    # Update user name
    resp = client.patch(
        f"/api/admin/users/{uid}",
        json={"name": "User2"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "User2"

    # Promote to admin via superadmin route
    resp = client.patch(
        f"/api/admin/users/{uid}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

    # Admin cannot create superadmin
    admin_token = client.post(
        "/api/auth/login", json={"email": "user@test.com", "password": "ValidPass123"}
    ).json()["token"]
    resp = client.post(
        "/api/admin/users",
        json={"email": "x@test.com", "name": "X", "role": "superadmin", "password": "ValidPass123", "active": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 403

    # Admin cannot change roles
    resp = client.patch(
        f"/api/admin/users/{uid}/role",
        json={"role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 403

    # List users
    resp = client.get("/api/admin/users", headers=headers)
    assert resp.status_code == 200
    assert any(u["email"] == "user@test.com" for u in resp.json())

    # User changes own password
    resp = client.post(
        "/api/auth/password",
        json={"old_password": "ValidPass123", "new_password": "NewPass12345"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 204
    # Old password fails, new password works
    assert (
        client.post("/api/auth/login", json={"email": "user@test.com", "password": "ValidPass123"}).status_code
        == 401
    )
    assert (
        client.post("/api/auth/login", json={"email": "user@test.com", "password": "NewPass12345"}).status_code
        == 200
    )

    # Deactivate user
    resp = client.patch(
        f"/api/admin/users/{uid}",
        json={"active": False},
        headers=headers,
    )
    assert resp.status_code == 200

    # Login should now fail
    resp = client.post("/api/auth/login", json={"email": "user@test.com", "password": "ValidPass123"})
    assert resp.status_code == 401
