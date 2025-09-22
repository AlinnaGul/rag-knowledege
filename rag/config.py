from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass
class MemoryConfig:
    # Where the SQLite file lives
    db_path: Path = Path("./data/memory/memory.db")

    # Short-term (per session)
    short_max_items: int = 30
    short_sim_threshold: float = 0.86

    # Long-term
    long_top_k: int = 5
    long_min_sim: float = 0.78
    promote_min_tokens: int = 40
    promote_on_questions: bool = True
