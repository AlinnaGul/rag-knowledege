from __future__ import annotations

"""Simple audit logging utilities."""

import datetime as dt
import json
import os
from pathlib import Path
from .middleware.correlation import request_id_ctx
from typing import Any

LOG_DIR = Path(os.getenv("LOGS_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "audit.log"


def log_action(
    action: str,
    user_id: int | None = None,
    collection_id: Any | None = None,
    doc_id: int | None = None,
) -> None:
    """Append an audit log entry to ``logs/audit.log``.

    Parameters:
        action: Name of the action (upload, index, query, unlink, purge)
        user_id: ID of the acting user
        collection_id: Related collection id or list of ids
        doc_id: Related document id
    """
    entry = {
        "timestamp": dt.datetime.utcnow().isoformat(),
        "action": action,
        "user_id": user_id,
        "collection_id": collection_id,
        "doc_id": doc_id,
        "request_id": request_id_ctx.get(None),
    }
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        # Logging should never raise; ignore errors
        pass
