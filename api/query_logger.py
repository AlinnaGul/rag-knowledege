from __future__ import annotations

"""Logging utilities for user queries and feedback."""

import datetime as dt
import json
import os
from pathlib import Path
from .middleware.correlation import request_id_ctx

LOG_DIR = Path(os.getenv("LOGS_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "queries.log"


def log_query(query_id: int, user_id: int, question: str, answer: str) -> None:
    entry = {
        "timestamp": dt.datetime.utcnow().isoformat(),
        "query_id": query_id,
        "user_id": user_id,
        "question": question,
        "answer": answer,
        "request_id": request_id_ctx.get(None),
    }
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def log_feedback(query_id: int, user_id: int, feedback: str) -> None:
    entry = {
        "timestamp": dt.datetime.utcnow().isoformat(),
        "query_id": query_id,
        "user_id": user_id,
        "feedback": feedback,
        "request_id": request_id_ctx.get(None),
    }
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
