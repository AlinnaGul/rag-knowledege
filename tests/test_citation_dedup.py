import os
import sys
import types

current_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("JWT_SECRET", "secret")

from rag import answerer  # type: ignore  # noqa: E402

def test_dedup_and_ranking():
    citations = [
        {"doc_id": 1, "title": "A", "page": 1, "chunk_id": "1a", "score": 0.2, "collection_id":1, "collection_name":"C", "snippet":"a"},
        {"doc_id": 1, "title": "A", "page": 1, "chunk_id": "1b", "score": 0.8, "collection_id":1, "collection_name":"C", "snippet":"b"},
        {"doc_id": 2, "title": "B", "page": 1, "chunk_id": "2a", "score": 0.5, "collection_id":1, "collection_name":"C", "snippet":"c"},
    ]
    ordered = answerer._rank_dedupe(citations)
    assert len(ordered) == 2
    assert ordered[0]["id"] == "1b"
    assert ordered[0]["score"] == 0.8
    assert ordered[1]["id"] == "2a"
