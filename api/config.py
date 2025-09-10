"""
Configuration and settings for the Data Nucleus application.

The settings are loaded from environment variables using pydantic-settings.
See `.env.example` in the project root for available variables.
"""
from __future__ import annotations

from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from rag.domain_config import DOMAIN_CONFIGS


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a .env file."""

    # OpenAI configuration
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    # Embedding backend configuration
    embedding_provider: str = Field(
        default="openai", alias="EMBEDDING_PROVIDER"
    )
    embedding_model: str = Field(
        default="text-embedding-3-large", alias="EMBEDDING_MODEL"
    )
    embedding_cache_db: str = Field(
        default="./data/embedding_cache.sqlite3",
        alias="EMBEDDING_CACHE_DB",
    )

    # Retrieval backend toggles
    use_bm25: bool = Field(default=False, alias="USE_BM25")
    bm25_index_dir: str = Field(default="./data/bm25", alias="BM25_INDEX_DIR")
    use_reranker: bool = Field(default=False, alias="USE_RERANKER")
    reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        alias="RERANKER_MODEL",
    )

    # JWT configuration
    jwt_secret: str = Field(alias="JWT_SECRET")
    access_token_expire_minutes: int = Field(
        default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )

    # CORS settings (comma-separated list)
    allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080",
        alias="ALLOWED_ORIGINS",
    )

    # Database configuration
    # NOTE: we keep your internal name `sql_database_uri` but accept env `SQLALCHEMY_DATABASE_URI`
    sql_database_uri: str = Field(default="sqlite:///data/app.db", alias="SQLALCHEMY_DATABASE_URI")

    # Chroma and file storage
    chroma_persist_dir: str = Field(default="./data/chroma", alias="CHROMA_PERSIST_DIR")
    raw_docs_dir: str = Field(default="./data/raw", alias="RAW_DOCS_DIR")
    collections_dir: str = Field(
        default="./data/collections", alias="COLLECTIONS_DIR"
    )

    # Ingestion and retrieval parameters
    max_upload_mb: int = Field(default=25, alias="MAX_UPLOAD_MB")
    top_k: int = Field(default=8, alias="TOP_K")
    mmr_lambda: float = Field(default=0.5, alias="MMR_LAMBDA")
    answer_temperature: float = Field(default=0.2, alias="ANSWER_TEMPERATURE")

    # Domain configuration
    domain: str = Field(default="manufacturing", alias="APP_DOMAIN")

    # Toggle asynchronous document indexing.  When enabled, newly uploaded or
    # linked documents are indexed in a background thread and a 202 Accepted
    # status code is returned from the API.  The indexing status can be
    # inspected via `/api/admin/documents/{id}/status`.
    async_indexing: bool = Field(default=False, alias="ASYNC_INDEXING")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,   # allow OPENAI_API_KEY or openai_api_key
        extra="ignore",         # ignore unknown env vars instead of erroring
        populate_by_name=True,  # allow using field names as well as aliases
    )


settings = Settings()

# Apply domain-specific retrieval defaults
_domain_cfg = DOMAIN_CONFIGS.get(settings.domain, DOMAIN_CONFIGS["manufacturing"])
for key, value in _domain_cfg.get("retrieval", {}).items():
    setattr(settings, key, value)
