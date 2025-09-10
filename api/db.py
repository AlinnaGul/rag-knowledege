"""
Database configuration for the Data Nucleus application.

This module sets up a SQLAlchemy engine and session factory based on the
configured database URI.  SQLite is supported out of the box.  A
`get_db` dependency is provided for FastAPI routes to get a scoped session.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings


# Determine connection arguments based on the database URI.  SQLite requires
# check_same_thread=False when used in a multi‑threaded application like
# FastAPI (uvicorn).  Other databases can omit this argument.
connect_args: dict[str, object] = {}
if settings.sql_database_uri.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# Create the SQLAlchemy engine and session factory.
engine = create_engine(settings.sql_database_uri, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models to inherit from.
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a database session and ensures it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()