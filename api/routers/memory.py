from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from .. import models

# import your store/manager (adjust import paths if you placed them under rag/memory)
from rag.memory.sql_store import SqlStore
from rag.memory.memory_manager import MemoryManager

router = APIRouter(prefix="/api/memory", tags=["memory"])

def _mgr() -> MemoryManager:
    store = SqlStore()  # uses MEM_DB_PATH or ./data/memory.sqlite
    return MemoryManager(store=store)

class CreateSessionRequest(BaseModel):
    title: Optional[str] = None

class SessionResponse(BaseModel):
    id: str
    title: Optional[str] = None

class MessageIn(BaseModel):
    role: str  # "user" | "assistant"
    content: str

class MessageOut(BaseModel):
    id: int
    role: str
    content: str

@router.post("/sessions", response_model=SessionResponse)
def create_session(
    req: CreateSessionRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    mgr = _mgr()
    sid = mgr.create_session(title=req.title or "Untitled", user_id=str(user.id))
    return SessionResponse(id=sid, title=req.title or "Untitled")

@router.get("/sessions/{session_id}/messages", response_model=List[MessageOut])
def list_messages(session_id: str, limit: int = 50):
    mgr = _mgr()
    msgs = mgr.get_messages(session_id, limit=limit)
    return [MessageOut(id=m["id"], role=m["role"], content=m["content"]) for m in msgs]

@router.post("/sessions/{session_id}/messages", response_model=MessageOut)
def add_message(session_id: str, msg: MessageIn):
    mgr = _mgr()
    mid = mgr.add_message(session_id, role=msg.role, content=msg.content)
    return MessageOut(id=mid, role=msg.role, content=msg.content)

@router.post("/sessions/{session_id}/summarize")
def summarize_session(session_id: str):
    mgr = _mgr()
    mgr.rollover_short_to_long(session_id)  # promotes short-term into long-term summary
    return {"ok": True}

@router.get("/sessions/{session_id}/summary")
def get_summary(session_id: str):
    mgr = _mgr()
    s = mgr.get_summary(session_id)
    return {"summary": s or ""}
