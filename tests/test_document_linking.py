import os
import sys
import io
from fastapi.testclient import TestClient
from pypdf import PdfWriter

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

    user_in = schemas.UserCreate(
        email="admin@test.com", name="Admin", password="AdminPass123", role="admin"
    )
    user = auth_service.create_user(db, user_in)
    token = auth_service.issue_access_token(user)
    return token, user.id


def test_upload_and_link(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore
    from api import models  # type: ignore

    client = TestClient(app)
    db = SessionLocal()
    token, admin_id = create_admin(db)
    headers = {"Authorization": f"Bearer {token}"}

    # create two collections
    c1 = models.Collection(name="A", description="", owner_id=admin_id)
    c2 = models.Collection(name="B", description="", owner_id=admin_id)
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1); db.refresh(c2)

    writer = PdfWriter(); writer.add_blank_page(width=72, height=72)
    pdf_io = io.BytesIO(); writer.write(pdf_io); pdf_bytes = pdf_io.getvalue()

    # upload to first collection
    resp = client.post(
        f"/api/admin/collections/{c1.id}/documents",
        headers=headers,
        files={"file": ("a.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    doc_id = resp.json()["uploads"][0]["document_id"]

    # link to second collection via document_id
    resp = client.post(
        f"/api/admin/collections/{c2.id}/documents/link",
        headers=headers,
        json={"document_id": doc_id},
    )
    assert resp.status_code == 204

    # check counts and that both links are indexed
    assert db.query(models.Blob).count() == 1
    assert db.query(models.Document).count() == 1
    assert db.query(models.DocumentChunk).count() >= 1
    links = db.query(models.DocumentCollection).all()
    assert len(links) == 2
    assert all(l.indexed_embedding_count > 0 for l in links)
