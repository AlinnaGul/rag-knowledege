from rag import retriever


def test_retriever_handles_mismatched_embedding(monkeypatch):
    # dummy client and collection with wrong embedding size
    class DummyCollection:
        def query(self, **kwargs):
            return {
                "documents": [["doc"]],
                "metadatas": [[{"chunk_id": "1"}]],
                "embeddings": [[[0.1, 0.2]]],
                "distances": [[0.0]],
            }

    class DummyClient:
        def get_or_create_collection(self, name: str):
            return DummyCollection()

    monkeypatch.setattr(retriever, "get_collection_client", lambda cid: DummyClient())
    monkeypatch.setattr(retriever.settings, "use_bm25", False)
    monkeypatch.setattr(retriever.settings, "use_reranker", False)

    r = retriever.Retriever()
    out = r.search("hello", allowed_collections=[1], k=1)
    assert out and out[0]["metadata"]["chunk_id"] == "1"

