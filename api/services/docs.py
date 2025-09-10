"""Service layer for document handling with content-addressed storage."""
from __future__ import annotations

import datetime as dt
import hashlib
import os
from pathlib import Path
from typing import Optional, Iterable
import json

from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import models
from ..config import settings
from ..db import SessionLocal
import threading
from ..audit import log_action
from rag import chunker


RAW_DIR = Path(settings.raw_docs_dir)
RAW_DIR.mkdir(parents=True, exist_ok=True)
COLL_META_DIR = Path(settings.collections_dir)
COLL_META_DIR.mkdir(parents=True, exist_ok=True)


def _set_status(link: models.DocumentCollection) -> None:
    """Update status and progress fields based on counts.

    This helper is used in places where the counts are directly manipulated
    (e.g. unlinking a document) to derive a reasonable state.  It avoids
    overriding explicit states like "embedding" or "failed" which are managed
    elsewhere.
    """
    if link.indexed_embedding_count and link.indexed_embedding_count > 0:
        link.status = "indexed"
        link.progress = 1.0
        link.error = None
    elif link.ingested_chunk_count and link.ingested_chunk_count > 0:
        if link.status not in ("embedding", "failed"):
            link.status = "extracting"
        link.progress = 0.5
        link.error = None
    else:
        if link.status != "failed":
            link.status = "queued"
        link.progress = 0.0


def _save_blob(db: Session, file: UploadFile) -> models.Blob:
    """Save uploaded file to storage, returning the blob record.

    If a blob with the same SHA-256 already exists, the file is discarded and the
    existing blob is returned.
    """
    hasher = hashlib.sha256()
    temp_path = RAW_DIR / (file.filename or "upload")
    with temp_path.open("wb") as out:
        while chunk := file.file.read(8192):
            out.write(chunk)
            hasher.update(chunk)
    sha = hasher.hexdigest()
    existing = db.query(models.Blob).filter_by(sha256=sha).first()
    if existing:
        temp_path.unlink(missing_ok=True)
        return existing
    dest_path = RAW_DIR / f"{sha}"
    os.replace(temp_path, dest_path)
    blob = models.Blob(
        sha256=sha,
        uri=str(dest_path),
        mime=file.content_type or "application/octet-stream",
        size_bytes=dest_path.stat().st_size,
    )
    db.add(blob)
    db.flush()
    return blob


def _ensure_chunk_cache(db: Session, blob: models.Blob) -> tuple[int, int]:
    existing = db.query(models.DocumentChunk).filter_by(blob_id=blob.id)
    if existing.first():
        chunk_count = existing.count()
        page_count = existing.with_entities(func.max(models.DocumentChunk.page)).scalar() or 1
        return page_count, chunk_count

    path = Path(blob.uri)
    chunks: list[models.DocumentChunk] = []
    pages: list[tuple[int, str]]
    suffix = path.suffix.lower()
    try:
        if blob.mime == "application/pdf" or suffix == ".pdf":
            pages = chunker.extract_text_from_pdf(str(path))
        elif suffix in {".doc", ".docx"} or blob.mime in {
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }:
            pages = chunker.extract_text_from_docx(str(path))
        else:
            pages = chunker.extract_text_from_txt(str(path))
    except Exception:
        pages = []

    page_count = max(len(pages), 1)
    if not pages:
        pages = [(1, "")]

    for idx, text in pages:
        chunks.append(
            models.DocumentChunk(
                blob_id=blob.id,
                section=None,
                page=idx,
                text=text,
                tokens=len(text.split()),
            )
        )

    db.add_all(chunks)
    db.flush()
    return page_count, len(chunks)


def _meta_path(collection_id: int, document_id: int) -> Path:
    return COLL_META_DIR / str(collection_id) / f"{document_id}.json"


def _write_link_meta(doc: models.Document, link: models.DocumentCollection) -> None:
    path = _meta_path(link.collection_id, doc.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "document_id": doc.id,
        "collection_id": link.collection_id,
        "title": doc.title,
        "ingested_chunk_count": link.ingested_chunk_count or 0,
        "indexed_embedding_count": link.indexed_embedding_count or 0,
        "updated_at": dt.datetime.utcnow().isoformat(),
    }
    path.write_text(json.dumps(data))


def _index_document(
    db: Session, doc: models.Document, collection_id: int, user_id: int | None = None
) -> None:
    link = db.query(models.DocumentCollection).filter_by(
        document_id=doc.id, collection_id=collection_id
    ).first()
    if not link:
        return
    chunks = db.query(models.DocumentChunk).filter_by(blob_id=doc.blob_id).all()
    if not chunks:
        link.indexed_embedding_count = 0
        link.indexed_at = dt.datetime.utcnow()
        _set_status(link)
        db.commit()
        _write_link_meta(doc, link)
        return

    # mark as embedding
    link.status = "embedding"
    link.progress = 0.75
    link.error = None
    db.flush()

    # --- embed and upsert into Chroma ---
    from rag.retriever import get_collection_client
    from rag.embeddings import get_embedder

    texts = [c.text for c in chunks]
    embedder = get_embedder()
    embeddings = embedder.embed(texts)

    client = get_collection_client(collection_id)
    chroma = client.get_or_create_collection(
        name="docs"
    )
    # Resolve collection name for metadata so citations can show human readable labels
    collection = (
        db.query(models.Collection).filter_by(id=collection_id).first()
    )
    collection_name = collection.name if collection else str(collection_id)
    # Remove any stale vectors for this document in this collection before re-indexing
    try:
        chroma.delete(where={"document_id": doc.id})
    except Exception:
        # Collection may be brand new; ignore deletion errors and proceed
        pass

    ids = [f"{doc.id}:{collection_id}:{i}" for i in range(len(chunks))]
    metadatas = []
    for i, c in enumerate(chunks):
        metadatas.append(
            {
                "document_id": doc.id,
                "doc_id": doc.id,
                "title": doc.title,
                "page": c.page,
                "chunk_id": ids[i],
                "collection_id": collection_id,
                "collection_name": collection_name,
            }
        )
    try:
        chroma.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        if settings.use_bm25:
            from rag import bm25

            bm25.index_chunks(collection_id, doc.id, ids, texts, metadatas)
        # Fetch stored vectors to ensure count reflects Chroma state
        res = chroma.get(where={"document_id": doc.id})
        link.indexed_embedding_count = len(res.get("ids", []))
        link.indexed_at = dt.datetime.utcnow()
        _set_status(link)
        db.commit()
        _write_link_meta(doc, link)
        log_action("index", user_id=user_id, collection_id=collection_id, doc_id=doc.id)
    except Exception as exc:  # pragma: no cover - network failures
        link.status = "failed"
        link.error = str(exc)
        db.commit()


def _async_index_document(doc_id: int, collection_id: int, user_id: int | None = None) -> None:
    """Background wrapper around `_index_document` that opens its own DB session."""
    db = SessionLocal()
    try:
        # Rehydrate the document instance
        doc = db.query(models.Document).filter_by(id=doc_id).first()
        if not doc:
            return
        _index_document(db, doc, collection_id, user_id=user_id)
    finally:
        db.close()


def save_document(db: Session, file: UploadFile, user: models.User, collection_id: int) -> models.Document:
    collection = (
        db.query(models.Collection)
        .filter_by(id=collection_id, is_deleted=False)
        .first()
    )
    if not collection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    blob = _save_blob(db, file)
    pages, chunk_count = _ensure_chunk_cache(db, blob)

    doc = db.query(models.Document).filter_by(blob_id=blob.id).first()
    if not doc:
        doc = models.Document(
            blob_id=blob.id,
            title=file.filename or "document",
            pages=pages,
            created_by=user.id,
        )
        db.add(doc)
        db.flush()
    elif doc.pages is None:
        doc.pages = pages

    link = (
        db.query(models.DocumentCollection)
        .filter_by(document_id=doc.id, collection_id=collection_id)
        .first()
    )
    if not link:
        link = models.DocumentCollection(document_id=doc.id, collection_id=collection_id)
        db.add(link)
        db.flush()
    link.ingested_chunk_count = chunk_count
    link.ingested_at = dt.datetime.utcnow()
    link.indexed_embedding_count = 0
    _set_status(link)
    db.flush()

    log_action("upload", user_id=user.id, collection_id=collection_id, doc_id=doc.id)
    # Start indexing.  When async_indexing is enabled the task is queued and a
    # separate thread performs the heavy lifting.
    if settings.async_indexing:
        link.status = "embedding"
        link.progress = 0.75
        db.commit()
        threading.Thread(
            target=_async_index_document,
            args=(doc.id, collection_id, user.id),
            daemon=True,
        ).start()
    else:
        _index_document(db, doc, collection_id, user_id=user.id)
    db.refresh(doc)
    return doc


def list_documents(db: Session, collection_id: int, q: str | None = None, page: int = 1, size: int = 10):
    query = (
        db.query(models.Document, models.Blob, models.DocumentCollection)
        .join(models.DocumentCollection, models.Document.id == models.DocumentCollection.document_id)
        .join(models.Blob, models.Document.blob_id == models.Blob.id)
        .filter(models.DocumentCollection.collection_id == collection_id)
        .order_by(models.DocumentCollection.created_at.desc())
    )
    if q:
        query = query.filter(models.Document.title.ilike(f"%{q}%"))
    total = query.count()
    items = query.offset((page - 1) * size).limit(size).all()
    result = []
    for doc, blob, link in items:
        result.append(
            {
                "document_id": doc.id,
                "title": doc.title,
                "mime": blob.mime,
                "size_bytes": blob.size_bytes,
                "pages": doc.pages,
                "status": link.status,
                "progress": link.progress,
                "error": link.error,
                "ingested_chunk_count": link.ingested_chunk_count,
                "indexed_embedding_count": link.indexed_embedding_count,
                "ingested_at": link.ingested_at,
                "indexed_at": link.indexed_at,
                "created_at": link.created_at,
            }
        )
    return {"items": result, "total": total}


def link_document(
    db: Session,
    collection_id: int,
    document_id: Optional[int] = None,
    sha256: Optional[str] = None,
    user: models.User | None = None,
) -> None:
    if document_id is None and sha256 is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document_id or sha256 required",
        )
    if document_id is not None:
        doc = db.query(models.Document).filter_by(id=document_id).first()
    else:
        blob = db.query(models.Blob).filter_by(sha256=sha256).first()
        doc = db.query(models.Document).filter_by(blob_id=blob.id).first() if blob else None
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    link = (
        db.query(models.DocumentCollection)
        .filter_by(document_id=doc.id, collection_id=collection_id)
        .first()
    )
    if not link:
        link = models.DocumentCollection(document_id=doc.id, collection_id=collection_id)
        db.add(link)
        db.flush()
    chunk_count = (
        db.query(func.count(models.DocumentChunk.id))
        .filter_by(blob_id=doc.blob_id)
        .scalar()
    )
    link.ingested_chunk_count = chunk_count
    link.ingested_at = dt.datetime.utcnow()
    link.indexed_embedding_count = 0
    _set_status(link)
    db.flush()
    # Either schedule or run indexing depending on async flag
    if settings.async_indexing:
        link.status = "embedding"
        link.progress = 0.75
        db.commit()
        threading.Thread(
            target=_async_index_document,
            args=(doc.id, collection_id, user.id if user else None),
            daemon=True,
        ).start()
    else:
        _index_document(db, doc, collection_id, user_id=user.id if user else None)


def update_document(
    db: Session,
    document_id: int,
    title: Optional[str] = None,
    meta: Optional[dict] = None,
    user: models.User | None = None,
) -> models.Document:
    doc = db.query(models.Document).filter_by(id=document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if title is not None:
        doc.title = title
    if meta is not None:
        doc.meta = str(meta)
    db.commit()
    db.refresh(doc)

    # Propagate renamed title to any existing embeddings and metadata
    links = db.query(models.DocumentCollection).filter_by(document_id=document_id).all()
    for link in links:
        try:
            _write_link_meta(doc, link)
            from rag.retriever import get_collection_client

            client = get_collection_client(link.collection_id)
            chroma = client.get_or_create_collection(name="docs")
            res = chroma.get(
                where={"document_id": document_id},
                include=["ids", "metadatas"],
            )
            ids = res.get("ids", [])
            metas = res.get("metadatas", [])
            if ids and metas:
                updated = []
                for m in metas:
                    m = m or {}
                    m["title"] = doc.title
                    updated.append(m)
                chroma.update(ids=ids, metadatas=updated)
        except Exception:
            # Ignore vector store failures to avoid blocking rename
            pass
    log_action("rename", user_id=user.id if user else None, doc_id=document_id)
    return doc


def unlink_document(
    db: Session, collection_id: int, document_id: int, user: models.User | None = None
) -> None:
    link = (
        db.query(models.DocumentCollection)
        .filter_by(document_id=document_id, collection_id=collection_id)
        .first()
    )
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
    # Remove vectors for this (document, collection) pair from Chroma
    from rag.retriever import get_collection_client

    client = get_collection_client(collection_id)
    chroma = client.get_or_create_collection(
        name="docs"
    )
    try:
        chroma.delete(where={"document_id": document_id})
    except Exception:
        pass

    # Clear counts so stats stay consistent before removing the link
    link.indexed_embedding_count = 0
    link.ingested_chunk_count = 0
    link.indexed_at = None
    link.ingested_at = None
    _set_status(link)
    db.flush()

    db.delete(link)
    db.commit()
    _meta_path(collection_id, document_id).unlink(missing_ok=True)
    log_action("unlink", user_id=user.id if user else None, collection_id=collection_id, doc_id=document_id)


def purge_document(db: Session, document_id: int, user: models.User | None = None) -> None:
    links = (
        db.query(models.DocumentCollection)
        .filter_by(document_id=document_id)
        .count()
    )
    if links:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="document still linked",
        )
    doc = db.query(models.Document).filter_by(id=document_id).first()
    if not doc:
        return
    blob = doc.blob
    # Remove any vectors for this document across collections
    from rag.retriever import get_collection_client

    # Remove vectors for this document from any collection directory that may exist
    base = Path(settings.chroma_persist_dir)
    if base.exists():
        for path in base.glob("coll_*"):
            try:
                cid = int(path.name.split("_", 1)[1])
            except (ValueError, IndexError):
                continue
            client = get_collection_client(cid)
            coll = client.get_or_create_collection(name="docs")
            try:
                coll.delete(where={"document_id": document_id})
            except Exception:
                pass

    db.delete(doc)
    db.flush()
    if blob and db.query(models.Document).filter_by(blob_id=blob.id).count() == 0:
        Path(blob.uri).unlink(missing_ok=True)
        db.query(models.DocumentChunk).filter_by(blob_id=blob.id).delete()
        db.delete(blob)
    db.commit()
    meta_base = COLL_META_DIR
    if meta_base.exists():
        for file in meta_base.glob(f"*/{document_id}.json"):
            file.unlink(missing_ok=True)
    log_action("purge", user_id=user.id if user else None, doc_id=document_id)


def reindex_document(
    db: Session, collection_id: int, document_id: int, user: models.User | None = None
) -> None:
    doc = db.query(models.Document).filter_by(id=document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    link = (
        db.query(models.DocumentCollection)
        .filter_by(document_id=document_id, collection_id=collection_id)
        .first()
    )
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not linked")
    link.indexed_embedding_count = 0
    link.indexed_at = None
    _set_status(link)
    db.flush()
    # Schedule or run indexing
    if settings.async_indexing:
        link.status = "embedding"
        link.progress = 0.75
        db.commit()
        threading.Thread(
            target=_async_index_document,
            args=(doc.id, collection_id, user.id if user else None),
            daemon=True,
        ).start()
    else:
        _index_document(db, doc, collection_id, user_id=user.id if user else None)
    log_action(
        "reindex",
        user_id=user.id if user else None,
        collection_id=collection_id,
        doc_id=document_id,
    )


def search_documents(
    db: Session, q: str | None = None, page: int = 1, size: int = 10
) -> dict:
    query = db.query(models.Document, models.Blob).join(models.Blob)
    if q:
        query = query.filter(models.Document.title.ilike(f"%{q}%"))
    total = query.count()
    rows = query.order_by(models.Document.created_at.desc()).offset((page - 1) * size).limit(size).all()
    items = []
    for doc, blob in rows:
        links = (
            db.query(models.DocumentCollection, models.Collection)
            .join(models.Collection)
            .filter(models.DocumentCollection.document_id == doc.id)
            .all()
        )
        coll_list = []
        for link, coll in links:
            coll_list.append(
                {
                    "collection_id": coll.id,
                    "collection_name": coll.name,
                    "status": link.status,
                    "progress": link.progress,
                }
            )
        items.append(
            {
                "document_id": doc.id,
                "title": doc.title,
                "mime": blob.mime,
                "size_bytes": blob.size_bytes,
                "pages": doc.pages,
                "sha256": blob.sha256,
                "collections": coll_list,
            }
        )
    return {"items": items, "total": total}


def collection_stats(db: Session, collection_id: int) -> dict:
    links = db.query(models.DocumentCollection).filter_by(collection_id=collection_id).all()
    doc_count = len(links)
    indexed_doc_count = sum(1 for l in links if l.indexed_embedding_count > 0)
    embedding_count = sum(l.indexed_embedding_count or 0 for l in links)
    by_doc = [
        {
            "document_id": l.document_id,
            "status": l.status,
            "ingested_chunk_count": l.ingested_chunk_count or 0,
            "indexed_embedding_count": l.indexed_embedding_count or 0,
        }
        for l in links
    ]
    return {
        "doc_count": doc_count,
        "indexed_doc_count": indexed_doc_count,
        "embedding_count": embedding_count,
        "by_doc": by_doc,
    }


def total_embeddings_for_collections(db: Session, collection_ids: Iterable[int]) -> int:
    return (
        db.query(func.coalesce(func.sum(models.DocumentCollection.indexed_embedding_count), 0))
        .filter(models.DocumentCollection.collection_id.in_(list(collection_ids)))
        .scalar()
    )
