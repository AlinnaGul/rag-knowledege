import os
import sys
from fastapi.testclient import TestClient

current_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def create_app(tmp_path):
    os.environ.setdefault("OPENAI_API_KEY", "test")
    os.environ.setdefault("JWT_SECRET", "secret")
    os.environ["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path/'app.db'}"
    os.environ["COLLECTIONS_DIR"] = str(tmp_path / "collections")
    os.environ["CHROMA_PERSIST_DIR"] = str(tmp_path / "chroma")
    os.environ["LOGS_DIR"] = str(tmp_path / "logs")
    import importlib
    import api.config as config  # type: ignore
    import api.db as db  # type: ignore
    import rag.retriever as retriever  # type: ignore
    import rag.answerer as answerer  # type: ignore
    import api.services.docs as docs  # type: ignore
    import api.query_logger as qlog  # type: ignore

    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(retriever)
    importlib.reload(answerer)
    importlib.reload(docs)
    importlib.reload(qlog)
    main = importlib.import_module("api.main")  # type: ignore
    importlib.reload(main)
    return main.create_app()


def create_admin(db):
    from api import schemas  # type: ignore
    from api.services import auth as auth_service  # type: ignore

    user_in = schemas.UserCreate(email="admin@test.com", name="Admin", password="AdminPass123", role="admin")
    user = auth_service.create_user(db, user_in)
    token = auth_service.issue_access_token(user)
    return user, token


def test_query_feedback(tmp_path):
    app = create_app(tmp_path)
    from api.db import SessionLocal  # type: ignore
    from api import models
    from api.services import docs as docs_service  # type: ignore
    from api.services import rag as rag_service  # type: ignore
    from rag import retriever as retriever_mod
    from rag import answerer as answerer_mod

    client = TestClient(app)
    db = SessionLocal()
    admin, token = create_admin(db)

    # create a collection so allowed list is non-empty
    coll = models.Collection(name="C1", description="", owner_id=admin.id)
    db.add(coll)
    db.commit(); db.refresh(coll)

    docs_service.total_embeddings_for_collections = lambda db, ids: 1

    class FakeRetriever:
        def search(self, *args, **kwargs):
            return []

    retriever_mod.Retriever = FakeRetriever
    answerer_mod.rewrite_question = lambda q: q
    answerer_mod.generate_answer = (
        lambda q, res, temperature=None, history=None: {
            "answer": "response", "citations": [], "latency_ms": 0
        }
    )
    rag_service.rewrite_question = answerer_mod.rewrite_question
    rag_service.generate_answer = answerer_mod.generate_answer

    sess = client.post(
        "/api/chat/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = sess.json()["id"]
    resp = client.post(
        "/api/ask",
        json={"question": "What?", "session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    qid = data["query_id"]
    db.close()
    db = SessionLocal()
    q = db.get(models.Query, qid)
    assert q.answer == "response"
    assert q.feedback is None

    resp = client.post(
        f"/api/queries/{qid}/feedback",
        json={"feedback": "up"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    db.refresh(q)
    assert q.feedback == "up"

    hist_resp = client.get(
        f"/api/chat/sessions/{session_id}/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hist_resp.status_code == 200
    history = hist_resp.json()
    assert history[0]["query_id"] == qid
    assert history[0]["feedback"] == "up"

    log_file = tmp_path / "logs" / "queries.log"
    contents = log_file.read_text().strip().splitlines()
    assert any("response" in line for line in contents)
    assert any("feedback" in line for line in contents)
