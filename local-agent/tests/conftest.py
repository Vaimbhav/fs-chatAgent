from __future__ import annotations

import contextlib
import hashlib
from typing import Any, Dict, List, Tuple

import pytest
from starlette.testclient import TestClient


class _DummyCollection:
    def __init__(self) -> None:
        # vid -> (document, metadata, embedding_vector)
        self._store: Dict[str, Tuple[str, Dict[str, Any], List[float]]] = {}

    # --- helpers ---
    @staticmethod
    def _emb(e: Any) -> List[float]:
        if isinstance(e, (list, tuple)):
            return [float(x) for x in e]
        return [0.0, 0.0, 0.0, 0.0]

    @staticmethod
    def _cos(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        num = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0.0 or nb == 0.0:
            return 0.0
        return num / (na * nb)

    def upsert(
        self,
        ids: List[str],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        embeddings: List[List[float]] | None = None,
    ) -> None:
        embeddings = embeddings or [[0.0, 0.0, 0.0, 0.0] for _ in documents]
        for i, vid in enumerate(ids):
            self._store[vid] = (documents[i], metadatas[i], self._emb(embeddings[i]))

    # legacy text-overlap scoring (used only if query_texts provided)
    @staticmethod
    def _text_score(q: str, text: str) -> float:
        qs = set(q.lower().split())
        ts = set(text.lower().split())
        return float(len(qs & ts)) + (len(text) / 1e6)

    def query(
        self,
        query_texts: List[str] | None = None,
        query_embeddings: List[List[float]] | None = None,
        n_results: int = 5,
        where: Dict[str, Any] | None = None,
        **_: Any,
    ):
        """
        Emulates Chroma's .query, supporting both query_texts and query_embeddings.
        Returns dict with ids, documents, metadatas, distances (we treat as similarity).
        """
        where = where or {}
        items = [(vid, doc, meta, emb) for vid, (doc, meta, emb) in self._store.items()
                 if all(meta.get(k) == v for k, v in where.items())]

        out_ids, out_docs, out_metas, out_scores = [], [], [], []

        if query_embeddings:
            for qemb in query_embeddings:
                scored = [ (self._cos(qemb, emb), vid, doc, meta) for vid, doc, meta, emb in items ]
                scored.sort(key=lambda t: t[0], reverse=True)
                top = scored[:n_results]
                out_ids.append([t[1] for t in top])
                out_docs.append([t[2] for t in top])
                out_metas.append([t[3] for t in top])
                out_scores.append([t[0] for t in top])
        else:
            qtexts = query_texts or [""]
            for q in qtexts:
                scored = [ (self._text_score(q, doc), vid, doc, meta) for vid, doc, meta, _emb in items ]
                scored.sort(key=lambda t: t[0], reverse=True)
                top = scored[:n_results]
                out_ids.append([t[1] for t in top])
                out_docs.append([t[2] for t in top])
                out_metas.append([t[3] for t in top])
                out_scores.append([t[0] for t in top])

        # match chroma key name used in your pipeline
        return {
            "ids": out_ids,
            "documents": out_docs,
            "metadatas": out_metas,
            "distances": out_scores,  # treated as similarity in your code
        }


@pytest.fixture
def _patch_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    (data_dir / "chroma").mkdir(parents=True, exist_ok=True)
    (data_dir / "checkpoints").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("CHROMA_DIR", str(data_dir / "chroma"))
    monkeypatch.setenv("CHECKPOINT_DIR", str(data_dir / "checkpoints"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return str(data_dir)


@pytest.fixture
def stub_embed_and_vs(monkeypatch):
    # stub vectorstore
    from agent_app import vectorstore as _vs_mod
    _singleton = _DummyCollection()
    monkeypatch.setattr(_vs_mod, "get_collection", lambda: _singleton, raising=True)

    # stub embedding: must accept self
    from agent_app import embedding as _emb_mod

    async def _fake_embed(self, texts: List[str]) -> List[List[float]]:
        vecs = []
        for t in texts:
            h = hashlib.sha1(t.encode("utf-8", errors="ignore")).digest()
            vecs.append([float(h[0]), float(h[1]), float(h[2]), float(h[3])])
        return vecs

    monkeypatch.setattr(_emb_mod.Embedder, "embed_texts", _fake_embed, raising=True)

    # stub LangGraph checkpointer to no-op so lifespan succeeds
    from langgraph.checkpoint.sqlite import aio as _aio_mod

    @contextlib.asynccontextmanager
    async def _noop_from_conn_string(_):
        yield None

    monkeypatch.setattr(_aio_mod.AsyncSqliteSaver, "from_conn_string", _noop_from_conn_string, raising=True)
    return _singleton


@pytest.fixture
def client(_patch_env, stub_embed_and_vs):
    from agent_app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def tmp_docs(tmp_path):
    d = tmp_path / "docs"
    d.mkdir(parents=True, exist_ok=True)
    return d
