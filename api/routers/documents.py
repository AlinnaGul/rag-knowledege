"""Administrative document endpoints with multi-collection support."""
from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_db, require_role
from .. import models
from ..services import docs as docs_service

router = APIRouter(prefix="/api/admin", tags=["documents"])


@router.get("/collections/{collection_id}/documents")
def list_collection_docs(collection_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_role("admin")), q: str | None = None, page: int = 1, size: int = 10):
    return docs_service.list_documents(db, collection_id, q=q, page=page, size=size)


@router.post("/collections/{collection_id}/documents")
def upload_document(
    collection_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    doc = docs_service.save_document(db, file, current_user, collection_id)
    return {"uploads": [{"document_id": doc.id, "status": "uploaded"}]}


@router.post("/collections/{collection_id}/documents/link", status_code=status.HTTP_204_NO_CONTENT)
def link_document(collection_id: int, payload: dict, db: Session = Depends(get_db), current_user: models.User = Depends(require_role("admin"))):
    docs_service.link_document(
        db,
        collection_id,
        payload.get("document_id"),
        payload.get("sha256"),
        user=current_user,
    )
    return None


@router.patch("/documents/{document_id}")
def update_document(document_id: int, payload: dict, db: Session = Depends(get_db), current_user: models.User = Depends(require_role("admin"))):
    doc = docs_service.update_document(
        db,
        document_id,
        title=payload.get("title"),
        meta=payload.get("meta"),
        user=current_user,
    )
    return {"id": doc.id, "title": doc.title, "meta": doc.meta}


@router.post(
    "/collections/{collection_id}/documents/{document_id}/reindex",
    status_code=status.HTTP_202_ACCEPTED,
)
def reindex_document(
    collection_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    docs_service.reindex_document(db, collection_id, document_id, user=current_user)
    return None


@router.delete("/collections/{collection_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_document(collection_id: int, document_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_role("admin"))):
    docs_service.unlink_document(db, collection_id, document_id, user=current_user)
    return None


@router.delete("/documents/{document_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
def purge_document(document_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(require_role("admin"))):
    docs_service.purge_document(db, document_id, user=current_user)
    return None


@router.get("/documents")
def search_documents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
    q: str | None = None,
    page: int = 1,
    size: int = 10,
):
    return docs_service.search_documents(db, q=q, page=page, size=size)


@router.get("/collections/{collection_id}/stats")
def collection_stats(
    collection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    return docs_service.collection_stats(db, collection_id)


# New endpoint: document status
@router.get("/documents/{document_id}/status")
def document_status(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("admin")),
):
    """Report ingestion/indexing progress for a document across all its collections."""
    links = (
        db.query(models.DocumentCollection)
        .filter_by(document_id=document_id)
        .all()
    )
    if not links:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    result = []
    for link in links:
        result.append(
            {
                "collection_id": link.collection_id,
                "status": link.status,
                "progress": link.progress,
                "error": link.error,
                "ingested_chunk_count": link.ingested_chunk_count or 0,
                "indexed_embedding_count": link.indexed_embedding_count or 0,
                "ingested_at": link.ingested_at,
                "indexed_at": link.indexed_at,
            }
        )
    return {"document_id": document_id, "collections": result}
