from __future__ import annotations

import logging
import os
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from .config import settings
from .models import Base

REQUIRED_COLUMNS = {
    "status": "TEXT DEFAULT 'queued'",
    "progress": "REAL DEFAULT 0.0",
    "error": "TEXT",
    "ingested_chunk_count": "INTEGER DEFAULT 0",
    "indexed_embedding_count": "INTEGER DEFAULT 0",
    "ingested_at": "DATETIME",
    "indexed_at": "DATETIME",
}

PREF_COLUMNS = {
    "mmr_lambda": "REAL DEFAULT 0.5",
}


def run_migrations(engine: Engine) -> None:
    """Ensure the database schema matches current models.

    Currently only handles adding missing columns to the document_collections table.
    For SQLite development databases, if migration fails the database is recreated
    from scratch with a clear log message.
    """
    with engine.begin() as conn:
        inspector = inspect(conn)

        # document_collections table
        if "document_collections" in inspector.get_table_names():
            existing_cols = {c["name"] for c in inspector.get_columns("document_collections")}
            missing = [col for col in REQUIRED_COLUMNS if col not in existing_cols]
            if missing:
                logging.info(
                    "Applying document_collections migrations: %s", ", ".join(missing)
                )
                for col in missing:
                    ddl = REQUIRED_COLUMNS[col]
                    try:
                        conn.execute(
                            text(f"ALTER TABLE document_collections ADD COLUMN {col} {ddl}")
                        )
                    except OperationalError:
                        logging.exception("Failed to add column %s", col)
                        uri = settings.sql_database_uri
                        if uri.startswith("sqlite"):
                            db_path = uri.replace("sqlite:///", "")
                            logging.warning(
                                "Recreating SQLite database at %s", db_path
                            )
                            conn.close()
                            if os.path.exists(db_path):
                                os.remove(db_path)
                            Base.metadata.create_all(bind=engine)
                        break

        # user_prefs table
        if "user_prefs" in inspector.get_table_names():
            existing = {c["name"] for c in inspector.get_columns("user_prefs")}
            missing_prefs = [col for col in PREF_COLUMNS if col not in existing]
            if missing_prefs:
                logging.info(
                    "Applying user_prefs migrations: %s", ", ".join(missing_prefs)
                )
                for col in missing_prefs:
                    ddl = PREF_COLUMNS[col]
                    try:
                        conn.execute(
                            text(f"ALTER TABLE user_prefs ADD COLUMN {col} {ddl}")
                        )
                    except OperationalError:
                        logging.exception("Failed to add column %s", col)
                        # don't nuke DB for prefs, just continue
                        break
