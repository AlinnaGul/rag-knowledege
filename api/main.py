"""
Entrypoint for the FastAPI application.

Creates the app, configures CORS, includes routers and initialises the
database.  This module is intended to be invoked by a WSGI/ASGI server
(e.g. uvicorn).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import engine
from .models import Base
from .migrations import run_migrations

from .routers import auth as auth_router
from .routers import documents as documents_router
from .routers import users as users_router
from .routers import ask as ask_router
from .routers import health as health_router
from .routers import collections as collections_router
from .routers import prefs as prefs_router
from .routers import chat as chat_router
from .routers import queries as queries_router
from .routers import chat_sessions as chat_sessions_router
from .routers import metrics as metrics_router
from .routers import me as me_router
from .middleware.disclaimer import DisclaimerMiddleware

try:
    # Optional middlewares may not exist during partial upgrades.  We guard
    # imports to avoid crashing if a module is missing.
    from .middleware.correlation import RequestIdMiddleware
except Exception:
    RequestIdMiddleware = None  # type: ignore

try:
    from .middleware.rate_limit import RateLimitMiddleware
except Exception:
    RateLimitMiddleware = None  # type: ignore

try:
    from .middleware.metrics import MetricsMiddleware
except Exception:
    MetricsMiddleware = None  # type: ignore


def create_app() -> FastAPI:
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    app = FastAPI(title="Data Nucleus Knowledge Hub API", version="0.1.0")
    # Configure CORS
    origins = [o.strip() for o in settings.allowed_origins.split(",")]
    import os
    origin_regex = os.getenv('ALLOWED_ORIGIN_REGEX', r'^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?$')
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization","Content-Type","Accept","Origin","X-Requested-With"],
        allow_origin_regex=origin_regex,
    )
    # Attach middleware for request correlation IDs, rate limiting and disclaimer
    if RequestIdMiddleware:
        app.add_middleware(RequestIdMiddleware)
    if RateLimitMiddleware:
        app.add_middleware(RateLimitMiddleware)
    if MetricsMiddleware:
        app.add_middleware(MetricsMiddleware)
    # Always attach disclaimer middleware
    app.add_middleware(DisclaimerMiddleware)
    # Include routers
    app.include_router(auth_router.router)
    app.include_router(documents_router.router)
    app.include_router(users_router.router)
    app.include_router(ask_router.router)
    app.include_router(health_router.router)
    app.include_router(collections_router.router)
    app.include_router(prefs_router.router)
    app.include_router(chat_router.router)
    app.include_router(queries_router.router)
    app.include_router(chat_sessions_router.router)
    app.include_router(metrics_router.router)
    app.include_router(me_router.router)

    @app.get("/")
    def root():
        return {"status": "ok"}
    return app


app = create_app()