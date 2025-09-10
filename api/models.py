"""
SQLAlchemy models for the Data Nucleus application.

These models represent users, documents, ingestion runs and query logs.  They
are defined using SQLAlchemy’s declarative API and mapped to tables via the
`Base` class in :mod:`api.db`.
"""
from __future__ import annotations

import datetime as _dt
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    Float,
    Index,
    Enum,
)
from sqlalchemy.orm import relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(
        Enum("user", "admin", "superadmin", name="role_enum"),
        nullable=False,
        default="user",
    )
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)

    # Relationships
    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")
    queries = relationship("Query", back_populates="user", cascade="all, delete-orphan")
    collections = relationship(
        "Collection", back_populates="owner", cascade="all, delete-orphan"
    )
    chat_history = relationship(
        "ChatHistory", back_populates="user", cascade="all, delete-orphan"
    )
    chat_sessions = relationship(
        "ChatSession", back_populates="user", cascade="all, delete-orphan"
    )


class Blob(Base):
    """Stored file information referenced by one or more documents."""

    __tablename__ = "blobs"

    id = Column(Integer, primary_key=True, index=True)
    sha256 = Column(String, unique=True, nullable=False)
    uri = Column(String, nullable=False)
    mime = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)

    documents = relationship("Document", back_populates="blob", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="blob", cascade="all, delete-orphan")


class Document(Base):
    """Logical document metadata pointing at a blob."""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    blob_id = Column(Integer, ForeignKey("blobs.id"), nullable=False)
    title = Column(String, nullable=False)
    pages = Column(Integer, nullable=True)
    meta = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)
    updated_at = Column(DateTime, default=_dt.datetime.utcnow)

    blob = relationship("Blob", back_populates="documents")
    owner = relationship("User", back_populates="documents")
    collections = relationship(
        "DocumentCollection", back_populates="document", cascade="all, delete-orphan"
    )


class Query(Base):
    __tablename__ = "queries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    feedback = Column(String, nullable=True)
    answer_len = Column(Integer, nullable=True)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)

    user = relationship("User", back_populates="queries")


class ChatHistory(Base):
    """Persisted chat exchanges for long-term memory."""

    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=True
    )
    query = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    query_id = Column(Integer, ForeignKey("queries.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)

    user = relationship("User", back_populates="chat_history")
    session = relationship("ChatSession", back_populates="history")
    query_ref = relationship("Query")


class ChatSession(Base):
    """A titled chat session containing many history entries."""

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_title = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)
    updated_at = Column(
        DateTime, default=_dt.datetime.utcnow, onupdate=_dt.datetime.utcnow
    )

    user = relationship("User", back_populates="chat_sessions")
    history = relationship(
        "ChatHistory", back_populates="session", cascade="all, delete-orphan"
    )


class Collection(Base):
    __tablename__ = "collections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    visibility = Column(String, default="private")
    is_deleted = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)
    updated_at = Column(DateTime, default=_dt.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("owner_id", "name", "is_deleted", name="uq_owner_name_active"),
    )

    owner = relationship("User", back_populates="collections")


class DocumentCollection(Base):
    """Link table for documents in collections with indexing status."""

    __tablename__ = "document_collections"

    document_id = Column(Integer, ForeignKey("documents.id"), primary_key=True)
    collection_id = Column(Integer, ForeignKey("collections.id"), primary_key=True)
    status = Column(String, default="queued")
    progress = Column(Float, default=0.0)
    error = Column(Text, nullable=True)
    ingested_chunk_count = Column(Integer, default=0)
    indexed_embedding_count = Column(Integer, default=0)
    ingested_at = Column(DateTime, nullable=True)
    indexed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)

    __table_args__ = (Index("idx_doccols_collection", "collection_id"),)

    document = relationship("Document", back_populates="collections")
    collection = relationship("Collection")


class DocumentChunk(Base):
    """Cached chunk extracted from a blob (shared across collections)."""

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    blob_id = Column(Integer, ForeignKey("blobs.id"), nullable=False, index=True)
    section = Column(String, nullable=True)
    page = Column(Integer, nullable=True)
    text = Column(Text, nullable=False)
    tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)

    __table_args__ = (Index("idx_chunks_blob", "blob_id"),)

    blob = relationship("Blob", back_populates="chunks")


class UserCollection(Base):
    """Mapping table for user access to collections."""

    __tablename__ = "user_collections"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    collection_id = Column(Integer, ForeignKey("collections.id"), primary_key=True)
    access_level = Column(String, default="read")
    created_at = Column(DateTime, default=_dt.datetime.utcnow)


class UserPrefs(Base):
    """Per-user preference settings."""

    __tablename__ = "user_prefs"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    temperature = Column(Float, default=0.2)
    top_k = Column(Integer, default=6)
    mmr_lambda = Column(Float, default=0.5)
    theme = Column(String, default="light")
    updated_at = Column(DateTime, default=_dt.datetime.utcnow, onupdate=_dt.datetime.utcnow)

    user = relationship("User")


# ---------------------------------------------------------------------------
# UserMemory
#
# Persist arbitrary facts or preferences associated with a user.  This table
# enables long‑term memory beyond chat history.  Each entry is keyed by a
# free‑form string and stores a corresponding value.  When new facts are
# learned from conversations they can be upserted here, and the RAG pipeline
# can retrieve them to augment the context.

class UserMemory(Base):
    __tablename__ = "user_memory"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    key = Column(String, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=_dt.datetime.utcnow, onupdate=_dt.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_user_memory_key"),
    )

    user = relationship("User")