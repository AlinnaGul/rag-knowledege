import os
import sys
import types

# Add project root to path for importing rag package
current_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Minimal env for settings import
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("JWT_SECRET", "secret")

from rag import answerer  # type: ignore  # noqa: E402


class FakeResp:
    def __init__(self, content: str = "ok") -> None:
        self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=content))]


def test_generate_answer_fills_missing_metadata(monkeypatch):
    monkeypatch.setattr(answerer.client.chat.completions, "create", lambda **_: FakeResp())

    contexts = [{"text": "text", "metadata": {}, "score": 0.5}]
    res = answerer.generate_answer("question", contexts)
    assert res["citations"]
    c = res["citations"][0]
    assert isinstance(c["id"], str)
    assert isinstance(c["filename"], str)
    assert isinstance(c["page"], int)
    assert isinstance(c["score"], float)
    assert isinstance(c["collection_id"], int)
    assert isinstance(c["collection_name"], str)
    assert isinstance(c["snippet"], str)
