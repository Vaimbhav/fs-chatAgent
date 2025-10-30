from __future__ import annotations
from typing import TypedDict, Any, List, Dict, Optional
import logging

from langgraph.graph import StateGraph, START, END

from agent_app.embedding import Embedder
from agent_app.vectorstore import get_collection
from agent_app.config import SETTINGS

log = logging.getLogger(__name__)


class QueryState(TypedDict, total=False):
    user_id: str
    query: str
    top_k: int
    filters: Dict[str, Any]
    model: Optional[str]
    hits: List[Dict[str, Any]]


async def retrieve(s: QueryState) -> QueryState:
    qtext = s.get("query", "") or ""
    if not qtext.strip():
        s["hits"] = []
        return s

    top_k = int(s.get("top_k", 10) or 10)
    raw_filters = s.get("filters") or {}
    where_filter = raw_filters if (isinstance(raw_filters, dict) and len(raw_filters) > 0) else None

    # Generate embeddings
    embedder = Embedder(model=s.get("model") or SETTINGS.embedding_model)
    qvec = (await embedder.embed_texts([qtext]))[0]

    # Query vector store
    col = get_collection()
    res = col.query(
        query_embeddings=[qvec],
        n_results=top_k,
        where=where_filter,
        include=["documents", "metadatas", "distances", "ids"],
    )

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    ids = (res.get("ids") or [[]])[0]

    hits = []
    for i, text in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        hits.append({
            "id": ids[i] if i < len(ids) else None,
            "text": text,
            "score": float(dists[i]) if i < len(dists) else None,
            "meta": meta,
            "path": meta.get("path") or meta.get("source"),
            "chunk_id": meta.get("chunk_id"),
            "file_type": meta.get("file_type"),
        })

    s["hits"] = hits
    return s


def build_graph(*, checkpointer=None):
    g = StateGraph(QueryState)
    g.add_node("retrieve", retrieve)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", END)
    return g.compile(checkpointer=checkpointer)


query_graph_api = build_graph(checkpointer=None)





# from __future__ import annotations
# from typing import TypedDict, Any, List, Dict, Optional
#
# from langgraph.graph import StateGraph, START, END
#
# from agent_app.embedding import Embedder
# from agent_app.vectorstore import get_collection
# from agent_app.config import SETTINGS
#
#
# class QueryState(TypedDict, total=False):
#     user_id: str
#     query: str
#     top_k: int
#     filters: Dict[str, Any]
#     model: Optional[str]
#     hits: List[Dict[str, Any]]
#
#
# async def retrieve(s: QueryState) -> QueryState:
#     qtext = s.get("query", "") or ""
#     if not qtext.strip():
#         s["hits"] = []
#         return s
#
#     top_k = int(s.get("top_k", 10) or 10)
#     raw_filters = s.get("filters") or {}
#
#     # ✅ Chroma doesn't accept an empty dict for `where`
#     where_filter = raw_filters if (isinstance(raw_filters, dict) and len(raw_filters) > 0) else None
#
#     embedder = Embedder(model=s.get("model") or SETTINGS.embedding_model)
#     qvec = (await embedder.embed_texts([qtext]))[0]
#
#     col = get_collection()
#     res = col.query(
#         query_embeddings=[qvec],
#         n_results=top_k,
#         where=where_filter,                   # <-- this was {} before
#         include=["documents", "metadatas", "distances"],  # no "ids" here
#     )
#
#     docs = (res.get("documents") or [[]])[0]
#     metas = (res.get("metadatas") or [[]])[0]
#     dists = (res.get("distances") or [[]])[0]
#     ids   = (res.get("ids") or [[]])[0]
#
#     hits = []
#     for i, text in enumerate(docs):
#         hits.append({
#             "id": ids[i] if i < len(ids) else None,
#             "text": text,
#             "score": dists[i] if i < len(dists) else None,
#             "meta": metas[i] if i < len(metas) else {},
#         })
#
#     s["hits"] = hits
#     return s
#
#
# def build_graph(*, checkpointer=None):
#     g = StateGraph(QueryState)
#     g.add_node("retrieve", retrieve)
#
#     g.add_edge(START, "retrieve")
#     g.add_edge("retrieve", END)
#
#     return g.compile(checkpointer=checkpointer)
#
#
# # Expose no-checkpointer graph for Studio (optional)
# query_graph_api = build_graph(checkpointer=None)
