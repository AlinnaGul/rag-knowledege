import io
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from test_document_lifecycle import create_app, create_admin


def test_documents_search_includes_collections(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore
    from api import models  # type: ignore

    client = TestClient(app)
    db = SessionLocal()
    token, admin_id = create_admin(db)
    headers = {"Authorization": f"Bearer {token}"}

    c1 = models.Collection(name="A", description="", owner_id=admin_id)
    c2 = models.Collection(name="B", description="", owner_id=admin_id)
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1); db.refresh(c2)

    writer = PdfWriter(); writer.add_blank_page(width=72, height=72)
    pdf_io = io.BytesIO(); writer.write(pdf_io); pdf_bytes = pdf_io.getvalue()

    resp = client.post(
        f"/api/admin/collections/{c1.id}/documents",
        headers=headers,
        files={"file": ("a.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    doc_id = resp.json()["uploads"][0]["document_id"]

    client.post(
        f"/api/admin/collections/{c2.id}/documents/link",
        headers=headers,
        json={"document_id": doc_id},
    )

    resp = client.get("/api/admin/documents", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["document_id"] == doc_id
    coll_ids = {c["collection_id"] for c in item["collections"]}
    assert coll_ids == {c1.id, c2.id}
    assert all("status" in c and "progress" in c for c in item["collections"])
