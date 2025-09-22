from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .config import MemoryConfig
from .sql_store import SqlStore
from .short_term_memory import ShortTermMemory
from .long_term_memory import LongTermMemory, MemoryEntry

@dataclass
class CacheHit:
    matched_text: str
    answer: str
    score: float

class MemoryManager:
    def __init__(self, cfg: Optional[MemoryConfig] = None) -> None:
        self.cfg = cfg or MemoryConfig()
        self.store = SqlStore(self.cfg.db_path)
        self.short = ShortTermMemory(self.store, max_items=self.cfg.short_max_items)
        self.long  = LongTermMemory(self.store)

    # BEFORE retrieval
    def check_short_term_cache(self, session_id: str, question: str) -> Optional[CacheHit]:
        sims = self.short.find_similar(session_id, question, top_k=1)
        if not sims: return None
        score, it = sims[0]
        if score >= self.cfg.short_sim_threshold:
            return CacheHit(matched_text=it["user_input"], answer=it["answer"], score=score)
        return None

    def fetch_long_term_hints(self, question: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.long.search(
            question,
            top_k=int(top_k or self.cfg.long_top_k),
            min_sim=float(self.cfg.long_min_sim),
        )

    # AFTER answer
    def record_interaction(self, session_id: str, question: str, answer: str) -> None:
        self.short.add(session_id, question, answer)
        if self.cfg.promote_on_questions and len(question.split()) >= self.cfg.promote_min_tokens:
            self.long.upsert([MemoryEntry(text=question, session_id=session_id, tags=["question"], importance=0.6)])

    def promote_custom_note(self, text: str, *, session_id: Optional[str] = None,
                            user_id: Optional[str] = None, tags: Optional[List[str]] = None,
                            importance: float = 0.7) -> None:
        self.long.upsert([MemoryEntry(text=text, session_id=session_id, user_id=user_id, tags=tags, importance=importance)])
