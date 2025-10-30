from __future__ import annotations
from typing_extensions import TypedDict
from typing import List, Dict, Any
import pathlib, mimetypes
from datetime import datetime

from langgraph.graph import StateGraph, START, END

from agent_app.db import init_db, SessionLocal
from agent_app.utils import sha256_bytes
from agent_app.chunking import chunk_text
from agent_app.embedding import Embedder
from agent_app.vectorstore import get_collection
from agent_app.config import SETTINGS
from agent_app.readers import is_supported_file, read_text_str

class IndexState(TypedDict, total=False):
    mode: str                 # "full" | "incremental"
    roots: List[str]
    model: str | None
    force_reembed: bool
    files: List[Dict[str, Any]]
    changed: List[Dict[str, Any]]
    chunks: List[Dict[str, Any]]
    embeddings: List[List[float]]
    stats: Dict[str, Any]
    errors: List[str]

def discover(s: IndexState) -> IndexState:
    files: list[dict] = []
    for root in s.get("roots", []):
        rp = pathlib.Path(root).expanduser()
        if not rp.exists():
            continue
        for p in rp.rglob("*"):
            if not p.is_file():
                continue
            if not is_supported_file(str(p)):
                continue
            st = p.stat()
            try:
                data = p.read_bytes()
                sha = sha256_bytes(data)
            except Exception:
                sha = f"sig:{st.st_size}:{st.st_mtime_ns}"
            files.append({
                "path": str(p),
                "bytes": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "sha256": sha,
                "mime": mimetypes.guess_type(str(p))[0] or "application/octet-stream",
                "ext": p.suffix.lower(),
            })
    s["files"] = files
    s.setdefault("stats", {})["discovered"] = len(files)
    return s

def diff(s: IndexState) -> IndexState:
    from sqlalchemy import text
    if s.get("force_reembed"):
        s["changed"] = list(s.get("files", []))
        s.setdefault("stats", {})["changed"] = len(s["changed"])
        return s
    changed: list[dict] = []
    mode = s.get("mode", "incremental")
    with SessionLocal() as db:
        known = {row[0]: row[1] for row in db.execute(text("SELECT path, sha256 FROM files"))}
    for f in s.get("files", []):
        if mode == "full" or f["path"] not in known or known[f["path"]] != f["sha256"]:
            changed.append(f)
    s["changed"] = changed
    s.setdefault("stats", {})["changed"] = len(changed)
    return s

def parse_chunk(s: IndexState) -> IndexState:
    texts: list[dict] = []
    for f in s.get("changed", []):
        try:
            data = read_text_str(f["path"])
        except Exception:
            data = ""
        if not data:
            s.setdefault("errors", []).append(f"parse-empty:{f['path']}")
            continue
        texts.append({"file": f, "text": data})

    s["chunks"] = []
    for t in texts:
        spans = chunk_text(t["text"], target_tokens=800, overlap=80)
        for idx, (cstart, cend, chunk) in enumerate(spans):
            s["chunks"].append({
                "file": t["file"],
                "chunk_idx": idx,
                "char_start": cstart,
                "char_end": cend,
                "text": chunk,
            })
    s.setdefault("stats", {})["chunks"] = len(s["chunks"])
    return s

async def embed_batch(s: IndexState) -> IndexState:
    if not s.get("chunks"):
        s["embeddings"] = []
        return s
    embedder = Embedder(model=s.get("model"))
    vecs: list[list[float]] = []
    B = 64
    texts = [c["text"] for c in s["chunks"]]
    for i in range(0, len(texts), B):
        vecs.extend(await embedder.embed_texts(texts[i:i+B]))
    s["embeddings"] = vecs
    return s

def upsert_vectors(s: IndexState) -> IndexState:
    col = get_collection()
    ids, docs, metas = [], [], []
    for c in s.get("chunks", []):
        f = c["file"]
        vid = f"{f['sha256']}:{c['chunk_idx']}"
        ids.append(vid)
        docs.append(c["text"])
        metas.append({
            "path": f["path"],
            "sha256": f["sha256"],
            "chunk_idx": c["chunk_idx"],
            "mime": f.get("mime"),
            "ext": f.get("ext"),
            "mtime_ns": f.get("mtime_ns"),
            "embedding_model": s.get("model") or SETTINGS.embedding_model,
        })
    if ids:
        col.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=s.get("embeddings", None))
    s.setdefault("stats", {})["upserted"] = len(ids)
    return s

def commit_run(s: IndexState) -> IndexState:
    from sqlalchemy import text
    now = datetime.utcnow().isoformat()
    with SessionLocal() as db:
        for f in s.get("changed", []):
            db.execute(text("""
            INSERT INTO files(path, bytes, mtime_ns, sha256, mime, last_indexed_at)
            VALUES(:path,:bytes,:mtime_ns,:sha256,:mime,:now)
            ON CONFLICT(path) DO UPDATE SET
              bytes=excluded.bytes, mtime_ns=excluded.mtime_ns, sha256=excluded.sha256,
              mime=excluded.mime, last_indexed_at=excluded.last_indexed_at
            """), {**f, "now": now})
        db.commit()
    return s

def build_graph(*, checkpointer=None):
    init_db()
    g = StateGraph(IndexState)
    g.add_node("discover", discover)
    g.add_node("diff", diff)
    g.add_node("parse_chunk", parse_chunk)
    g.add_node("embed_batch", embed_batch)
    g.add_node("upsert_vectors", upsert_vectors)
    g.add_node("commit_run", commit_run)

    g.add_edge(START, "discover")
    g.add_edge("discover", "diff")
    g.add_edge("diff", "parse_chunk")
    g.add_edge("parse_chunk", "embed_batch")
    g.add_edge("embed_batch", "upsert_vectors")
    g.add_edge("upsert_vectors", "commit_run")
    g.add_edge("commit_run", END)

    return g.compile(checkpointer=checkpointer)

# For Studio (no checkpointer; the API wires one)
index_graph_api = build_graph(checkpointer=None)
