import io
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from test_document_lifecycle import create_app, create_admin


def test_document_actions(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore
    from api import models  # type: ignore

    client = TestClient(app)
    db = SessionLocal()
    token, admin_id = create_admin(db)
    headers = {"Authorization": f"Bearer {token}"}

    c1 = models.Collection(name="A", description="", owner_id=admin_id)
    db.add(c1)
    db.commit()
    db.refresh(c1)

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    pdf_io = io.BytesIO()
    writer.write(pdf_io)
    pdf_bytes = pdf_io.getvalue()

    resp = client.post(
        f"/api/admin/collections/{c1.id}/documents",
        headers=headers,
        files={"file": ("a.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    doc_id = resp.json()["uploads"][0]["document_id"]

    resp = client.patch(
        f"/api/admin/documents/{doc_id}",
        headers=headers,
        json={"title": "Renamed"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed"

    resp = client.post(
        f"/api/admin/collections/{c1.id}/documents/{doc_id}/reindex",
        headers=headers,
    )
    assert resp.status_code == 202

    resp = client.delete(
        f"/api/admin/collections/{c1.id}/documents/{doc_id}",
        headers=headers,
    )
    assert resp.status_code == 204

    resp = client.delete(
        f"/api/admin/documents/{doc_id}/purge",
        headers=headers,
    )
    assert resp.status_code == 204

    resp = client.get("/api/admin/documents", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []
