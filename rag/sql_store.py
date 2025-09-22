from __future__ import annotations

import json, sqlite3, math, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# --- helpers -------------------------------------------------
def _vec_to_json(vec: Optional[Iterable[float]]) -> str:
    return json.dumps(list(vec or []), ensure_ascii=False)

def _json_to_vec(s: Optional[str]) -> List[float]:
    if not s: return []
    try: return [float(x) for x in json.loads(s)]
    except Exception: return []

def _cos(u: List[float], v: List[float]) -> float:
    if not u or not v: return 0.0
    s = sum(a*b for a,b in zip(u,v))
    nu = math.sqrt(sum(a*a for a in u)); nv = math.sqrt(sum(b*b for b in v))
    if nu == 0 or nv == 0: return 0.0
    return s/(nu*nv)

# --- store ---------------------------------------------------
class SqlStore:
    """
    Single-file SQLite store for short- and long-term memory.
    Tables:
      interactions(session_id TEXT, ts REAL, user_input TEXT, answer TEXT, q_vec TEXT)
      memories(id TEXT PRIMARY KEY, text TEXT, session_id TEXT, user_id TEXT, tags TEXT, importance REAL, emb TEXT)
    """
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_path)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=30, isolation_level=None)  # autocommit

    def _init(self) -> None:
        with self._conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS interactions(
                    session_id TEXT,
                    ts REAL,
                    user_input TEXT,
                    answer TEXT,
                    q_vec TEXT
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_inter_s ON interactions(session_id, ts)")
            con.execute("""
                CREATE TABLE IF NOT EXISTS memories(
                    id TEXT PRIMARY KEY,
                    text TEXT,
                    session_id TEXT,
                    user_id TEXT,
                    tags TEXT,
                    importance REAL,
                    emb TEXT
                )
            """)

    # -------- short-term ------------
    def add_interaction(self, session_id: str, user_input: str, answer: str, q_vec: List[float]) -> None:
        with self._conn() as con:
            con.execute(
                "INSERT INTO interactions(session_id, ts, user_input, answer, q_vec) VALUES(?,?,?,?,?)",
                (session_id, time.time(), user_input, answer, _vec_to_json(q_vec)),
            )
            # keep only last N
            con.execute("""
                DELETE FROM interactions
                WHERE session_id=? AND ts NOT IN (
                    SELECT ts FROM interactions WHERE session_id=? ORDER BY ts DESC LIMIT ?
                )
            """, (session_id, session_id, 30))

    def recent_interactions(self, session_id: str, n: int) -> List[Dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT ts, user_input, answer, q_vec FROM interactions WHERE session_id=? ORDER BY ts DESC LIMIT ?",
                (session_id, n),
            ).fetchall()
        out = []
        for ts, q, a, v in rows:
            out.append({"ts": ts, "user_input": q, "answer": a, "q_vec": _json_to_vec(v)})
        return out

    def most_similar_interaction(self, session_id: str, q_vec: List[float]) -> Optional[Tuple[float, Dict[str,Any]]]:
        # brute force in Python (datasets are small)
        items = self.recent_interactions(session_id, n=300)
        scored = [( _cos(q_vec, it.get("q_vec", [])), it) for it in items]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0] if scored else None

    # -------- long-term ------------
    def upsert_memories(self, entries: List[Dict[str, Any]]) -> None:
        if not entries: return
        with self._conn() as con:
            for e in entries:
                con.execute("""
                    INSERT INTO memories(id, text, session_id, user_id, tags, importance, emb)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                      text=excluded.text,
                      session_id=excluded.session_id,
                      user_id=excluded.user_id,
                      tags=excluded.tags,
                      importance=excluded.importance,
                      emb=excluded.emb
                """, (
                    e["id"], e["text"], e.get("session_id"), e.get("user_id"),
                    json.dumps(e.get("tags", []), ensure_ascii=False),
                    float(e.get("importance", 0.5)), _vec_to_json(e.get("emb", []))
                ))

    def all_memories(self) -> List[Dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute("SELECT id, text, session_id, user_id, tags, importance, emb FROM memories").fetchall()
        out = []
        for i,t,s,u,tg,imp,em in rows:
            out.append({"id": i, "text": t, "session_id": s, "user_id": u,
                        "tags": json.loads(tg or "[]"), "importance": float(imp),
                        "emb": _json_to_vec(em)})
        return out

    def topk_similar_memories(self, q_vec: List[float], k: int) -> List[Tuple[float, Dict[str, Any]]]:
        items = self.all_memories()
        scored = [( _cos(q_vec, it.get("emb", [])), it) for it in items]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:k]
