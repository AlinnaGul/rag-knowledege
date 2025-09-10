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


def create_admin(db):
    from api import schemas  # type: ignore
    from api.services import auth as auth_service  # type: ignore

    user_in = schemas.UserCreate(
        email="admin@test.com", name="Admin", password="AdminPass123", role="admin"
    )
    user = auth_service.create_user(db, user_in)
    token = auth_service.issue_access_token(user)
    return token, user.id


def test_document_lifecycle(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore
    from api import models  # type: ignore
    from rag.retriever import get_collection_client

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
    meta1 = tmp_path / "collections" / str(c1.id) / f"{doc_id}.json"
    assert meta1.exists()

    # list docs to ensure indexed and counts present
    resp = client.get(
        f"/api/admin/collections/{c1.id}/documents",
        headers=headers,
    )
    item = resp.json()["items"][0]
    assert item["status"] == "indexed"
    assert item["ingested_chunk_count"] > 0
    assert item["indexed_embedding_count"] > 0

    chroma1 = get_collection_client(c1.id).get_or_create_collection("docs")
    res = chroma1.get(where={"document_id": doc_id}, include=["metadatas"])
    ids_before = res.get("ids", [])
    assert len(ids_before) == item["indexed_embedding_count"]
    # ensure per-collection storage directory has data
    path1 = tmp_path / "chroma" / f"coll_{c1.id}"
    assert (path1 / "chroma.sqlite3").exists()

    resp = client.post(
        f"/api/admin/collections/{c1.id}/documents/{doc_id}/reindex",
        headers=headers,
    )
    assert resp.status_code == 202
    res2 = chroma1.get(where={"document_id": doc_id})
    assert len(res2.get("ids", [])) == len(ids_before)
    assert set(res2.get("ids", [])) == set(ids_before)

    # stats
    resp = client.get(
        f"/api/admin/collections/{c1.id}/stats",
        headers=headers,
    )
    stats = resp.json()
    assert stats["doc_count"] == 1
    assert stats["embedding_count"] > 0
    assert stats["by_doc"][0]["ingested_chunk_count"] > 0
    assert stats["by_doc"][0]["indexed_embedding_count"] > 0

    # rename
    resp = client.patch(
        f"/api/admin/documents/{doc_id}",
        headers=headers,
        json={"title": "renamed.pdf"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "renamed.pdf"

    # link to second collection
    resp = client.post(
        f"/api/admin/collections/{c2.id}/documents/link",
        headers=headers,
        json={"document_id": doc_id},
    )
    assert resp.status_code == 204
    assert db.query(models.Blob).count() == 1
    assert db.query(models.Document).count() == 1
    assert db.query(models.DocumentChunk).count() >= 1
    chroma2 = get_collection_client(c2.id).get_or_create_collection("docs")
    chroma2 = get_collection_client(c2.id).get_or_create_collection("docs")
    res = chroma2.get(where={"document_id": doc_id})
    assert len(res.get("ids", [])) > 0
    meta2 = tmp_path / "collections" / str(c2.id) / f"{doc_id}.json"
    assert meta2.exists()
    stats_c2 = client.get(
        f"/api/admin/collections/{c2.id}/stats",
        headers=headers,
    ).json()
    assert stats_c2["embedding_count"] > 0
    stats_c1_before_unlink = client.get(
        f"/api/admin/collections/{c1.id}/stats",
        headers=headers,
    ).json()

    # unlink from second collection
    resp = client.delete(
        f"/api/admin/collections/{c2.id}/documents/{doc_id}",
        headers=headers,
    )
    assert resp.status_code == 204
    chroma2 = get_collection_client(c2.id).get_or_create_collection("docs")
    res = chroma2.get(where={"document_id": doc_id})
    assert len(res.get("ids", [])) == 0
    assert not meta2.exists()
    stats_c2_after = client.get(
        f"/api/admin/collections/{c2.id}/stats",
        headers=headers,
    ).json()
    assert stats_c2_after["embedding_count"] == 0
    stats_c1_after = client.get(
        f"/api/admin/collections/{c1.id}/stats",
        headers=headers,
    ).json()
    assert stats_c1_after["embedding_count"] == stats_c1_before_unlink["embedding_count"]

    # purge fails while linked to c1
    resp = client.delete(
        f"/api/admin/documents/{doc_id}/purge",
        headers=headers,
    )
    assert resp.status_code == 409

    # unlink from c1 then purge
    client.delete(
        f"/api/admin/collections/{c1.id}/documents/{doc_id}",
        headers=headers,
    )
    resp = client.delete(
        f"/api/admin/documents/{doc_id}/purge",
        headers=headers,
    )
    assert resp.status_code == 204
    assert db.query(models.Document).count() == 0
    assert db.query(models.Blob).count() == 0
    chroma1 = get_collection_client(c1.id).get_or_create_collection("docs")
    res = chroma1.get(where={"document_id": doc_id})
    assert len(res.get("ids", [])) == 0
    assert not meta1.exists()
