from __future__ import annotations

from fastapi import FastAPI, HTTPException, Body, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Any, Optional, Union, List, Dict
from contextlib import asynccontextmanager
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

import traceback, logging, time, json, os, re, httpx, asyncio

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent_app.db import (
    init_db, ensure_user, log_query_record, log_query_hits_records,
    log_api_event, log_web_results, log_web_fetches,
)
from agent_app.config import SETTINGS
from agent_app.graphs.index_graph import build_graph as build_index_graph
from agent_app.graphs.query_graph import build_graph as build_query_graph
from agent_app.vectorstore import get_collection

log = logging.getLogger(__name__)


# ========== MODELS ==========
class IndexRequest(BaseModel):
    roots: Optional[Union[List[str], str]] = None
    force_reembed: bool = False
    model: Optional[str] = None


class SearchRequest(BaseModel):
    user_id: str
    query: str
    top_k: int = 10
    filters: dict[str, Any] | None = None


class UnifiedResult(BaseModel):
    """Unified search result from local or web"""
    source: str  # "local" or "web"
    title: str
    content: str
    url: Optional[str] = None
    score: float
    metadata: Dict[str, Any] = {}


# ========== HELPER FUNCTIONS ==========
def _normalize_roots(val, default_roots):
    if val is None:
        return list(default_roots)
    if isinstance(val, str):
        return [val]
    return [str(p) for p in val]


def _lg_config(*, thread_id: str, run_id: Optional[str] = None) -> dict:
    cfg = {"configurable": {"thread_id": thread_id}}
    if run_id:
        cfg["configurable"]["run_id"] = run_id
    return cfg


# ========== RELEVANCE SCORING ==========
def calculate_relevance_score(query: str, text: str, title: str = "") -> float:
    """
    Calculate relevance score between query and text/title.
    Returns a score between 0 and 1.
    """
    query_lower = query.lower().strip()
    text_lower = text.lower().strip()
    title_lower = title.lower().strip()

    combined = f"{title_lower} {text_lower}"

    # 1. Exact phrase match in title (highest priority)
    if query_lower in title_lower:
        return 1.0

    # 2. Exact phrase match in content
    if query_lower in text_lower:
        return 0.95

    # 3. All query terms present
    query_terms = set(query_lower.split())
    combined_terms = set(combined.split())

    if len(query_terms) > 0:
        matching_terms = query_terms.intersection(combined_terms)
        term_coverage = len(matching_terms) / len(query_terms)
    else:
        term_coverage = 0

    # 4. Term frequency boost
    term_freq_score = 0
    for term in query_terms:
        term_freq_score += combined.count(term)
    term_freq_score = min(term_freq_score / (len(query_terms) * 3), 1.0)

    # 5. Sequence similarity (for partial matches)
    sequence_sim = SequenceMatcher(None, query_lower, combined[:1000]).ratio()

    # Combined score (weighted)
    combined_score = (
            term_coverage * 0.5 +
            term_freq_score * 0.3 +
            sequence_sim * 0.2
    )

    return min(combined_score, 1.0)


def normalize_local_results(hits: List[Dict], query: str) -> List[UnifiedResult]:
    """Convert local file search hits to unified format"""
    results = []

    for hit in hits:
        content = hit.get("text", "") or hit.get("content", "")
        path = hit.get("path", "") or hit.get("meta", {}).get("path", "")
        file_name = path.split("/")[-1] if path else "Local Document"

        # Recalculate relevance based on content
        relevance = calculate_relevance_score(query, content, file_name)

        # Boost score if original vector score was high
        original_score = hit.get("score", 0)
        if original_score and original_score < 0.5:  # cosine distance < 0.5 is good
            relevance = relevance * 1.2

        results.append(UnifiedResult(
            source="local",
            title=file_name,
            content=content[:500],  # First 500 chars
            url=f"file://{path}" if path else None,
            score=min(relevance, 1.0),
            metadata={
                "path": path,
                "original_score": original_score,
                "chunk_id": hit.get("chunk_id"),
                "file_type": hit.get("file_type") or hit.get("meta", {}).get("file_type"),
                "full_text": content  # Keep full text for potential use
            }
        ))

    return results


def normalize_web_results(results: List[Dict], query: str) -> List[UnifiedResult]:
    """Convert web search results to unified format"""
    normalized = []

    for idx, result in enumerate(results):
        snippet = result.get("snippet", "") or result.get("text", "")
        title = result.get("title", "")

        # Position-based score (earlier results get higher base score)
        position_score = max(0.5, 1.0 - (idx * 0.08))

        # Content relevance score
        content_score = calculate_relevance_score(query, snippet, title)

        # Combined web score (trust search engine ranking but verify with content)
        final_score = (position_score * 0.4) + (content_score * 0.6)

        normalized.append(UnifiedResult(
            source="web",
            title=title,
            content=snippet[:500],
            url=result.get("url"),
            score=final_score,
            metadata={
                "published_date": result.get("publishedDate"),
                "search_engine": result.get("source"),
                "position": idx + 1,
                "full_text": result.get("text")  # If scraped
            }
        ))

    return normalized


def merge_and_rank_results(
        local_results: List[UnifiedResult],
        web_results: List[UnifiedResult],
        strategy: str = "balanced",
        max_results: int = 10
) -> List[UnifiedResult]:
    """
    Intelligently merge and rank results from both sources

    Strategies:
    - "balanced": Mix local and web based on relevance
    - "local_first": Prioritize local, then web
    - "web_first": Prioritize web, then local
    - "interleaved": Alternate between sources
    """

    # Apply strategy-based score adjustments
    if strategy == "local_first":
        for r in local_results:
            r.score = min(r.score * 1.3, 1.0)
    elif strategy == "web_first":
        for r in web_results:
            r.score = min(r.score * 1.3, 1.0)
    elif strategy == "interleaved":
        # Interleave results
        merged = []
        max_len = max(len(local_results), len(web_results))
        for i in range(max_len):
            if i < len(local_results):
                merged.append(local_results[i])
            if i < len(web_results):
                merged.append(web_results[i])
        return merged[:max_results]

    # Combine all results
    all_results = local_results + web_results

    # Remove duplicates (same URL or very similar content)
    unique_results = []
    seen_urls = set()
    seen_content_fingerprints = set()

    for result in sorted(all_results, key=lambda x: x.score, reverse=True):
        # Check URL uniqueness
        if result.url and result.url in seen_urls:
            continue

        # Check content similarity (first 200 chars as fingerprint)
        content_fp = result.content[:200].lower().strip()
        if content_fp in seen_content_fingerprints:
            continue

        unique_results.append(result)

        if result.url:
            seen_urls.add(result.url)
        if content_fp:
            seen_content_fingerprints.add(content_fp)

        # Stop if we have enough results
        if len(unique_results) >= max_results:
            break

    # Final sort by score
    unique_results.sort(key=lambda x: x.score, reverse=True)

    return unique_results[:max_results]


# ========== LIFESPAN ==========
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    os.makedirs(SETTINGS.checkpoint_dir, exist_ok=True)

    index_db = os.path.abspath(os.path.join(SETTINGS.checkpoint_dir, "index.sqlite"))
    query_db = os.path.abspath(os.path.join(SETTINGS.checkpoint_dir, "query.sqlite"))

    async with AsyncSqliteSaver.from_conn_string(index_db) as index_cp, \
            AsyncSqliteSaver.from_conn_string(query_db) as query_cp:
        app.state.index_graph = build_index_graph(checkpointer=index_cp)
        app.state.query_graph = build_query_graph(checkpointer=query_cp)
        log.info("Application started successfully")
        yield
        log.info("Application shutting down")


app = FastAPI(title="Local Agent with Unified Search", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:2024", "http://127.0.0.1:2024"
    ],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


# ========== BASIC ENDPOINTS ==========
@app.get("/", include_in_schema=False)
def root():
    return {"message": "Local Agent API with Unified Search", "docs": "/docs"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/v1/health")
async def health_check():
    """System health check"""
    issues = []

    # Check vector store
    try:
        stats = get_collection_stats()
        vstore_status = stats.get("status", "unknown")
        doc_count = stats.get("document_count", 0)
    except Exception as e:
        vstore_status = "error"
        doc_count = 0
        issues.append({"component": "vectorstore", "error": str(e)})

    # Check API keys
    openai_key = bool(os.getenv("OPENAI_API_KEY", "").strip())
    if not openai_key:
        issues.append({"component": "openai", "error": "OPENAI_API_KEY not set"})

    return {
        "status": "healthy" if not issues else "degraded",
        "components": {
            "vectorstore": {"status": vstore_status, "documents": doc_count},
            "openai": {"configured": openai_key},
            "web_search": {
                "exa": bool(os.getenv("EXA_API_KEY")),
                "serper": bool(os.getenv("SERPER_API_KEY"))
            }
        },
        "issues": issues
    }


# ========== FILE UPLOAD ==========
@app.post("/api/v1/upload-files")
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload and index multiple files"""
    upload_dir = "uploaded_files"
    os.makedirs(upload_dir, exist_ok=True)

    file_paths = []
    errors = []

    for file in files:
        try:
            file_path = os.path.join(upload_dir, file.filename)
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            file_paths.append(file_path)
            log.info(f"Uploaded: {file.filename} ({len(content)} bytes)")
        except Exception as e:
            errors.append({"file": file.filename, "error": str(e)})
            log.error(f"Failed to save {file.filename}: {e}")

    if not file_paths:
        raise HTTPException(400, {"message": "No files uploaded", "errors": errors})

    # Index files
    try:
        state = {
            "mode": "incremental",
            "roots": file_paths,
            "model": None,
            "force_reembed": True,
            "stats": {},
            "errors": []
        }
        cfg = _lg_config(thread_id=f"upload:{int(time.time() * 1000)}", run_id="batch-upload")

        t0 = time.perf_counter()
        result = await app.state.index_graph.ainvoke(state, config=cfg)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        stats = result.get("stats", {}) or {}
        index_errors = result.get("errors", []) or []

        log.info(f"Indexed {len(file_paths)} files in {latency_ms}ms")

        return {
            "message": f"{len(file_paths)} files uploaded and indexed",
            "files": [os.path.basename(p) for p in file_paths],
            "stats": stats,
            "errors": index_errors + errors,
            "latency_ms": latency_ms
        }

    except Exception as e:
        log.exception("Indexing failed")
        raise HTTPException(500, {
            "message": "Files uploaded but indexing failed",
            "files": [os.path.basename(p) for p in file_paths],
            "error": str(e)
        })


# ========== INDEXING ENDPOINTS ==========
@app.post("/api/v1/index-full")
async def index_full(req: Optional[IndexRequest] = Body(None)):
    """Full re-index of all documents"""
    roots = _normalize_roots(req.roots if req else None, SETTINGS.default_roots)
    if not roots:
        raise HTTPException(400, "No roots provided")

    state = {
        "mode": "full",
        "roots": roots,
        "model": (req.model if req else None),
        "force_reembed": True,
        "stats": {}, "errors": []
    }
    cfg = _lg_config(thread_id=f"index:{int(time.time() * 1000)}", run_id="index-full")

    t0 = time.perf_counter()
    result = await app.state.index_graph.ainvoke(state, config=cfg)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    stats = result.get("stats", {}) or {}
    errors = result.get("errors", []) or []

    scanned_files = sorted({f.get("path") for f in (result.get("files") or []) if f.get("path")})
    changed_files = sorted({f.get("path") for f in (result.get("changed") or []) if f.get("path")})
    unchanged_files = sorted(set(scanned_files) - set(changed_files))

    log.info(f"Index FULL: {len(scanned_files)} files, {len(changed_files)} changed")

    event_id = log_api_event(
        user_id="system", api="/api/v1/index-full",
        request_obj={"roots": roots},
        response_obj={"stats": stats, "changed": len(changed_files)},
        status="ok" if not errors else "warning",
        latency_ms=latency_ms, notes="full_reindex"
    )

    return {
        "roots": roots,
        "stats": stats,
        "errors": errors,
        "scanned_files": scanned_files,
        "changed_files": changed_files,
        "unchanged_files": unchanged_files,
        "event_id": event_id,
        "latency_ms": latency_ms
    }


@app.post("/api/v1/index")
async def index_incremental(req: Optional[IndexRequest] = Body(None)):
    """Incremental index (only changed files)"""
    try:
        roots = _normalize_roots(req.roots if req else None, SETTINGS.default_roots)
        if not roots:
            raise HTTPException(400, "No roots provided")

        state = {
            "mode": "incremental",
            "roots": roots,
            "model": (req.model if req else None),
            "force_reembed": bool(getattr(req, "force_reembed", False)),
            "stats": {}, "errors": []
        }
        cfg = _lg_config(thread_id=f"index:{int(time.time() * 1000)}", run_id="index-inc")

        t0 = time.perf_counter()
        result = await app.state.index_graph.ainvoke(state, config=cfg)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        stats = result.get("stats", {}) or {}
        errors = result.get("errors", []) or []

        scanned_files = sorted({f.get("path") for f in (result.get("files") or []) if f.get("path")})
        changed_files = sorted({f.get("path") for f in (result.get("changed") or []) if f.get("path")})
        unchanged_files = sorted(set(scanned_files) - set(changed_files))

        log.info(f"Index INCREMENTAL: {len(scanned_files)} files, {len(changed_files)} changed")

        event_id = log_api_event(
            user_id="system", api="/api/v1/index",
            request_obj={"roots": roots},
            response_obj={"stats": stats, "changed": len(changed_files)},
            status="ok" if not errors else "warning",
            latency_ms=latency_ms, notes="incremental_index"
        )

        # If you need rf_counter, call it here
        rf_counter()

        file_paths = scanned_files  # define file_paths for return

        return {
            "roots": roots,
            "stats": stats,
            "errors": errors,
            "scanned_files": scanned_files,
            "changed_files": changed_files,
            "unchanged_files": unchanged_files,
            "event_id": event_id,
            "latency_ms": latency_ms,
            "message": f"{len(file_paths)} files uploaded and indexed",
            "files": [os.path.basename(p) for p in file_paths]
        }

    except Exception as e:
        log.exception("Indexing failed")
        raise HTTPException(500, {
            "message": "Files uploaded but indexing failed",
            "files": scanned_files if 'scanned_files' in locals() else [],
            "error": str(e)
        })


# ========== LOCAL SEARCH ==========
@app.post("/api/v1/file/search")
async def search(req: SearchRequest):
    """Search local indexed files"""
    t0 = time.perf_counter()

    try:
        ensure_user(req.user_id, None)

        qstate = {
            "user_id": req.user_id,
            "query": req.query,
            "top_k": req.top_k,
            "filters": req.filters
        }
        cfg = _lg_config(thread_id=f"query:{req.user_id}", run_id=f"q-{int(time.time() * 1000)}")

        result = await app.state.query_graph.ainvoke(qstate, config=cfg)
        hits = result.get("hits", []) or []

        latency_ms = int((time.perf_counter() - t0) * 1000)

        qid = log_query_record(
            user_id=req.user_id, qtext=req.query, top_k=req.top_k,
            filters_json=json.dumps(req.filters) if req.filters else None,
            model=None, latency_ms=latency_ms,
            response_json=json.dumps({"hits": hits}, ensure_ascii=False)
        )
        log_query_hits_records(qid, hits)

        return {"query_id": qid, "latency_ms": latency_ms, "hits": hits}

    except Exception as e:
        log.exception("Search failed")
        raise HTTPException(500, {
            "message": "Search failed",
            "error": str(e),
            "hint": "Check that files are indexed and OPENAI_API_KEY is set"
        })


# ========== WEB SEARCH HELPERS ==========
async def _exa_search(query_text: str, top_n: int, include_text: bool) -> list[dict]:
    api_key = os.getenv("EXA_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(400, "EXA_API_KEY missing")

    payload = {"query": query_text, "numResults": max(1, min(top_n, 10))}
    if include_text:
        payload["text"] = True

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post("https://api.exa.ai/search", headers={
            "x-api-key": api_key, "Content-Type": "application/json"
        }, json=payload)
        r.raise_for_status()

        results = []
        for it in r.json().get("results", []):
            results.append({
                "title": it.get("title"),
                "url": it.get("url"),
                "snippet": it.get("text") or it.get("description"),
                "publishedDate": it.get("publishedDate"),
                "source": "exa",
                "text": it.get("text") if include_text else None,
            })
        return results


async def _serper_search(query_text: str, top_n: int) -> list[dict]:
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(400, "SERPER_API_KEY missing")

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post("https://google.serper.dev/search", headers={
            "X-API-KEY": api_key, "Content-Type": "application/json"
        }, json={"q": query_text, "num": max(1, min(top_n, 10))})
        r.raise_for_status()

        results = []
        for it in r.json().get("organic", []):
            results.append({
                "title": it.get("title"),
                "url": it.get("link"),
                "snippet": it.get("snippet"),
                "source": "serper"
            })
        return results


@app.get("/api/v1/web/search")
async def web_search(
        engine: str = Query(...),
        q: str = Query(None),
        query: str = Query(None),
        data: bool = Query(False),
        top_n: int = Query(3, ge=1, le=10),
        user_id: str = Query("anonymous")
):
    """Web search endpoint"""
    qtxt = (q or query or "").strip()
    if not qtxt:
        raise HTTPException(400, "Missing query")

    ensure_user(user_id, None)

    engines = [e.strip() for e in re.split(r"[|,]", engine) if e.strip()]
    results = []

    for eng in engines:
        try:
            if eng == "exa":
                results = await _exa_search(qtxt, top_n, data)
            elif eng == "serper":
                results = await _serper_search(qtxt, top_n)
            break
        except Exception as e:
            log.error(f"Engine {eng} failed: {e}")
            continue

    return {"engine": engines[0] if results else None, "q": qtxt, "results": results}


# ========== UNIFIED SEARCH (MAIN FEATURE) ==========
@app.post("/api/v1/search/unified")
async def unified_search(
        search_req: SearchRequest,
        strategy: str = Query("balanced", description="balanced|local_first|web_first|interleaved"),
        web_engine: str = Query("serper|exa"),
        web_top_n: int = Query(3, ge=1, le=10),
        include_web: bool = Query(True),
        max_results: int = Query(10, ge=1, le=50)
):
    """
    🎯 INTELLIGENT UNIFIED SEARCH

    Combines local file search and web search, then:
    1. Normalizes both result sets
    2. Calculates relevance scores
    3. Removes duplicates
    4. Ranks by strategy
    5. Returns best results
    """
    t0 = time.pe

# from __future__ import annotations
#
# from fastapi import FastAPI, HTTPException, Body, Query
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import Response
# from pydantic import BaseModel
# from typing import Any, Optional, Union, List
# from contextlib import asynccontextmanager
# from bs4 import BeautifulSoup
#
# from fastapi import UploadFile, File
#
# import traceback, logging, time, json, os, re, httpx
#
# from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
#
# from agent_app.db import (
#     init_db, ensure_user, log_query_record, log_query_hits_records,
#     log_api_event, log_web_results, log_web_fetches,
# )
# from agent_app.config import SETTINGS
# from agent_app.graphs.index_graph import build_graph as build_index_graph
# from agent_app.graphs.query_graph import build_graph as build_query_graph
#
# log = logging.getLogger(__name__)
#
#
# # -------------------------
# # Observability helpers (NO logic changes to indexing)
# # -------------------------
# def _log_watching_paths(roots: list[str]) -> None:
#     """Log which roots will be scanned. Purely observational."""
#     for r in roots:
#         abspath = os.path.abspath(r)
#         kind = "dir" if os.path.isdir(abspath) else ("file" if os.path.isfile(abspath) else "missing")
#         print(f"[index] watching path: {abspath} ({kind})")
#         try:
#             log.info(f"[index] watching path: {abspath} ({kind})")
#         except Exception:
#             pass
#
#
# def _log_discovered_files(roots: list[str]) -> None:
#     """
#     Log files discovered under the provided roots (non-intrusive; read-only).
#     This does not filter by MIME or change what your graphs index.
#     """
#     for r in roots:
#         abspath = os.path.abspath(r)
#         if os.path.isfile(abspath):
#             try:
#                 size = os.path.getsize(abspath)
#             except Exception:
#                 size = "?"
#             print(f"[index] discovered file: {abspath} ({size} bytes)")
#             try:
#                 log.info(f"[index] discovered file: {abspath} ({size} bytes)")
#             except Exception:
#                 pass
#             continue
#
#         if os.path.isdir(abspath):
#             for dirpath, dirnames, filenames in os.walk(abspath, followlinks=False):
#                 for fname in filenames:
#                     fpath = os.path.join(dirpath, fname)
#                     try:
#                         size = os.path.getsize(fpath)
#                     except Exception:
#                         size = "?"
#                     print(f"[index] discovered file: {fpath} ({size} bytes)")
#                     try:
#                         log.info(f"[index] discovered file: {fpath} ({size} bytes)")
#                     except Exception:
#                         pass
#         else:
#             print(f"[index] path not found (skipping): {abspath}")
#             try:
#                 log.warning(f"[index] path not found (skipping): {abspath}")
#             except Exception:
#                 pass
#
#
# # ---------- Models ----------
# class IndexRequest(BaseModel):
#     roots: Optional[Union[List[str], str]] = None
#     force_reembed: bool = False  # ignored for /index-full (forced True)
#     model: Optional[str] = None
#
#
# class SearchRequest(BaseModel):
#     user_id: str
#     query: str
#     top_k: int = 10
#     filters: dict[str, Any] | None = None
#
#
# # ---------- Helpers ----------
# def _normalize_roots(val, default_roots):
#     if val is None:
#         return list(default_roots)
#     if isinstance(val, str):
#         return [val]
#     return [str(p) for p in val]
#
#
# def _lg_config(*, thread_id: str, run_id: Optional[str] = None) -> dict:
#     cfg = {"configurable": {"thread_id": thread_id}}
#     if run_id:
#         cfg["configurable"]["run_id"] = run_id
#     return cfg
#
#
# def _group_scanned_by_root(paths: list[str], roots: list[str]) -> dict[str, list[str]]:
#     """Group scanned file paths by their root for terminal logging."""
#     groups: dict[str, list[str]] = {r: [] for r in roots}
#     abs_roots = [(r, os.path.abspath(r)) for r in roots]
#     for p in paths:
#         pa = os.path.abspath(p)
#         matched_root = None
#         for r_orig, r_abs in abs_roots:
#             if pa == r_abs or pa.startswith(r_abs + os.sep):
#                 matched_root = r_orig
#                 break
#         groups.setdefault(matched_root or "<other>", []).append(p)
#     return groups
#
#
# # ---------- Lifespan ----------
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     init_db()
#     os.makedirs(SETTINGS.checkpoint_dir, exist_ok=True)
#
#     index_db = os.path.abspath(os.path.join(SETTINGS.checkpoint_dir, "index.sqlite"))
#     query_db = os.path.abspath(os.path.join(SETTINGS.checkpoint_dir, "query.sqlite"))
#
#     async with AsyncSqliteSaver.from_conn_string(index_db) as index_cp, \
#             AsyncSqliteSaver.from_conn_string(query_db) as query_cp:
#         app.state.index_graph = build_index_graph(checkpointer=index_cp)
#         app.state.query_graph = build_query_graph(checkpointer=query_cp)
#         yield
#
#
# app = FastAPI(title="Local Agent (SQLite-logged)", lifespan=lifespan)
#
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[
#         "http://localhost:3000", "http://127.0.0.1:3000",
#         "http://localhost:5173", "http://127.0.0.1:5173",
#         "http://localhost:2024", "http://127.0.0.1:2024"
#     ],
#     allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
# )
#
#
# @app.get("/", include_in_schema=False)
# def root():
#     return {"message": "Welcome to the Local Agent API! Use /docs for documentation."}
#
#
# @app.get("/favicon.ico", include_in_schema=False)
# def favicon():
#     return Response(status_code=204)
#
#
# # ---------- Indexing ----------
# @app.post("/api/v1/index-full")
# async def index_full(req: Optional[IndexRequest] = Body(None)):
#     roots = _normalize_roots(req.roots if req else None, SETTINGS.default_roots)
#     if not roots:
#         raise HTTPException(status_code=400, detail="No roots provided. Pass 'roots' or set INDEX_ROOTS in .env")
#
#     # _log_watching_paths(roots)  # log which roots are being scanned
#     # _log_discovered_files(roots)  # log which files were found under those roots
#
#     state = {
#         "mode": "full",
#         "roots": roots,
#         "model": (req.model if req else None),
#         "force_reembed": True,  # hard reset behavior
#         "stats": {}, "errors": []
#     }
#     cfg = _lg_config(thread_id=f"index:{int(time.time() * 1000)}", run_id="index-full")
#
#     t0 = time.perf_counter()
#     result = await app.state.index_graph.ainvoke(state, config=cfg)
#     latency_ms = int((time.perf_counter() - t0) * 1000)
#
#     stats = result.get("stats", {}) or {}
#     errors = result.get("errors", []) or []
#
#     # NEW: collect discovered (all scanned), changed, unchanged
#     scanned_files = sorted({f.get("path") for f in (result.get("files") or []) if f.get("path")})
#     changed_files = sorted({f.get("path") for f in (result.get("changed") or []) if f.get("path")})
#     unchanged_files = sorted(set(scanned_files) - set(changed_files))
#
#     # Terminal log: per-root file listing
#     log.info("Index FULL scan roots: %s", roots)
#     grouped = _group_scanned_by_root(scanned_files, roots)
#     for r, lst in grouped.items():
#         log.info("  Root: %s  (%d files)", r, len(lst))
#         for path in lst:
#             log.info("    - %s", path)
#     log.info("  Changed: %d | Unchanged: %d", len(changed_files), len(unchanged_files))
#
#     # DB log event
#     event_id = log_api_event(
#         user_id="system",
#         api="/api/v1/index-full",
#         request_obj={"roots": roots, "force_reembed": True, "model": state["model"]},
#         response_obj={
#             "stats": stats,
#             "changed_files": changed_files,
#             "unchanged_files": unchanged_files,
#         },
#         status="ok" if not errors else "warning",
#         latency_ms=latency_ms,
#         notes="full reindex",
#     )
#
#     return {
#         "roots": roots,
#         "stats": stats,
#         "errors": errors,
#         "scanned_files": scanned_files,  # NEW
#         "changed_files": changed_files,  # existing
#         "unchanged_files": unchanged_files,  # NEW
#         "event_id": event_id,
#         "latency_ms": latency_ms,
#     }
#
#
# @app.post("/api/v1/index")
# async def index_incremental(req: Optional[IndexRequest] = Body(None)):
#     roots = _normalize_roots(req.roots if req else None, SETTINGS.default_roots)
#     if not roots:
#         raise HTTPException(status_code=400, detail="No roots provided. Pass 'roots' or set INDEX_ROOTS in .env")
#
#     # _log_watching_paths(roots)  # log which roots are being scanned
#     # _log_discovered_files(roots)  # log which files were found under those roots
#
#     state = {
#         "mode": "incremental",
#         "roots": roots,
#         "model": (req.model if req else None),
#         "force_reembed": bool(getattr(req, "force_reembed", False)),
#         "stats": {}, "errors": []
#     }
#     cfg = _lg_config(thread_id=f"index:{int(time.time() * 1000)}", run_id="index-inc")
#
#     t0 = time.perf_counter()
#     result = await app.state.index_graph.ainvoke(state, config=cfg)
#     latency_ms = int((time.perf_counter() - t0) * 1000)
#
#     stats = result.get("stats", {}) or {}
#     errors = result.get("errors", []) or []
#
#     # NEW: collect discovered (all scanned), changed, unchanged
#     scanned_files = sorted({f.get("path") for f in (result.get("files") or []) if f.get("path")})
#     changed_files = sorted({f.get("path") for f in (result.get("changed") or []) if f.get("path")})
#     unchanged_files = sorted(set(scanned_files) - set(changed_files))
#
#     # Terminal log: per-root file listing
#     log.info("Index INCREMENTAL scan roots: %s", roots)
#     grouped = _group_scanned_by_root(scanned_files, roots)
#     for r, lst in grouped.items():
#         log.info("  Root: %s  (%d files)", r, len(lst))
#         for path in lst:
#             log.info("    - %s", path)
#     log.info("  Changed: %d | Unchanged: %d", len(changed_files), len(unchanged_files))
#
#     # DB log event
#     event_id = log_api_event(
#         user_id="system",
#         api="/api/v1/index",
#         request_obj={"roots": roots, "force_reembed": state["force_reembed"], "model": state["model"]},
#         response_obj={
#             "stats": stats,
#             "changed_files": changed_files,
#             "unchanged_files": unchanged_files,
#         },
#         status="ok" if not errors else "warning",
#         latency_ms=latency_ms,
#         notes="incremental index",
#     )
#
#     return {
#         "roots": roots,
#         "stats": stats,
#         "errors": errors,
#         "scanned_files": scanned_files,  # NEW
#         "changed_files": changed_files,  # existing
#         "unchanged_files": unchanged_files,  # NEW
#         "event_id": event_id,
#         "latency_ms": latency_ms,
#     }
#
#
# # ---------- Local file search (JSON body) ----------
# @app.post("/api/v1/file/search")
# async def search(req: SearchRequest):
#     t0 = time.perf_counter()
#     try:
#         ensure_user(req.user_id, None)
#         qstate = {"user_id": req.user_id, "query": req.query, "top_k": req.top_k, "filters": req.filters}
#         cfg = _lg_config(thread_id=f"query:{req.user_id}", run_id=f"q-{int(time.time() * 1000)}")
#         result = await app.state.query_graph.ainvoke(qstate, config=cfg)
#         hits = result.get("hits", []) or []
#         latency_ms = int((time.perf_counter() - t0) * 1000)
#
#         resp_json = json.dumps({"hits": hits}, ensure_ascii=False)
#         qid = log_query_record(
#             user_id=req.user_id, qtext=req.query, top_k=req.top_k,
#             filters_json=json.dumps(req.filters) if req.filters else None,
#             model=None, latency_ms=latency_ms, response_json=resp_json
#         )
#         log_query_hits_records(qid, hits)
#         return {"query_id": qid, "latency_ms": latency_ms, "hits": hits}
#     except Exception as e:
#         log.exception("Search failed")
#         raise HTTPException(status_code=400, detail={
#             "message": "Search failed",
#             "hint": "Check OPENAI_API_KEY and that the index contains documents.",
#             "error": str(e),
#             "traceback": traceback.format_exc().splitlines()[-3:],
#         })
#
#
# # ---------- Web Search (POST; user_id in query params) ----------
# VALID_ENGINES = {"exa", "serper"}
#
#
# def _parse_engines(engine_param: str) -> list[str]:
#     """
#     Accepts: "exa", "serper", "exa|serper", "serper,exa".
#     Returns a de-duplicated, validated list IN THE GIVEN ORDER.
#     """
#     if not engine_param or not engine_param.strip():
#         raise HTTPException(status_code=400, detail="engine is required (exa, serper, or 'exa|serper').")
#     parts = [t.strip().lower() for t in re.split(r"[|,]", engine_param) if t.strip()]
#     if not parts:
#         raise HTTPException(status_code=400, detail="engine list is empty")
#     engines: list[str] = []
#     for p in parts:
#         if p not in VALID_ENGINES:
#             raise HTTPException(status_code=400, detail=f"unknown engine '{p}'. Allowed: exa, serper")
#         if p not in engines:
#             engines.append(p)
#     return engines[:3]
#
#
# def _pick_query(q: str | None, query: str | None) -> str:
#     qtxt = (q or query or "").strip()
#     if not qtxt:
#         raise HTTPException(status_code=400, detail="Missing query. Pass q=... or query=...")
#     return qtxt
#
#
# async def _extract_text_from_url(client: httpx.AsyncClient, url: str, timeout: float = 12.0) -> dict:
#     try:
#         r = await client.get(url, timeout=timeout, follow_redirects=True, headers={
#             "User-Agent": "Mozilla/5.0 (compatible; LocalAgent/1.0; +https://localhost)"
#         })
#         r.raise_for_status()
#         html = r.text
#         soup = BeautifulSoup(html, "html.parser")
#         for tag in soup(["script", "style", "noscript"]):
#             tag.decompose()
#         for sel in ["header", "nav", "footer", "aside"]:
#             for t in soup.select(sel):
#                 t.decompose()
#         text = " ".join(soup.get_text(separator=" ").split())
#         return {"ok": True, "text": text[:200000], "length": len(text), "status": r.status_code, "url": url}
#     except Exception as e:
#         return {"ok": False, "error": str(e), "url": url}
#
#
# async def _exa_search(query_text: str, top_n: int, include_text: bool) -> list[dict]:
#     api_key = os.getenv("EXA_API_KEY", "").strip()
#     if not api_key:
#         raise HTTPException(status_code=400, detail="EXA_API_KEY missing in environment")
#     base = "https://api.exa.ai"
#     payload = {"query": query_text, "numResults": max(1, min(top_n, 10))}
#     if include_text:
#         payload["text"] = True
#     async with httpx.AsyncClient(timeout=15.0) as client:
#         r = await client.post(f"{base}/search", headers={
#             "x-api-key": api_key,
#             "Content-Type": "application/json",
#         }, json=payload)
#         r.raise_for_status()
#         j = r.json()
#         results = []
#         for it in j.get("results", []):
#             results.append({
#                 "title": it.get("title"),
#                 "url": it.get("url"),
#                 "snippet": it.get("text") or it.get("description") or it.get("highlight"),
#                 "publishedDate": it.get("publishedDate"),
#                 "source": "exa",
#                 "text": it.get("text") if include_text else None,
#             })
#         return results
#
#
# async def _serper_search(query_text: str, top_n: int) -> list[dict]:
#     api_key = os.getenv("SERPER_API_KEY", "").strip()
#     if not api_key:
#         raise HTTPException(status_code=400, detail="SERPER_API_KEY missing in environment")
#     url = "https://google.serper.dev/search"
#     body = {"q": query_text, "num": max(1, min(top_n, 10))}
#     async with httpx.AsyncClient(timeout=15.0) as client:
#         r = await client.post(url, headers={
#             "X-API-KEY": api_key,
#             "Content-Type": "application/json",
#         }, json=body)
#         r.raise_for_status()
#         j = r.json()
#         results = []
#         for it in j.get("organic", []):
#             results.append({
#                 "title": it.get("title"),
#                 "url": it.get("link"),
#                 "snippet": it.get("snippet"),
#                 "source": "serper",
#             })
#         return results
#
#
# async def _maybe_scrape(results: list[dict], top_n: int) -> tuple[list[dict], list[dict]]:
#     if not results:
#         return results, []
#     logs = []
#     top = results[:top_n]
#     async with httpx.AsyncClient(timeout=15.0) as client:
#         for item in top:
#             url = item.get("url")
#             if not url:
#                 continue
#             got = await _extract_text_from_url(client, url)
#             if got.get("ok"):
#                 item["text"] = got["text"]
#                 item["scrape_status"] = got["status"]
#                 item["text_length"] = got["length"]
#             else:
#                 item["scrape_error"] = got.get("error")
#             logs.append(got)
#     return results, logs
#
#
# @app.get("/api/v1/web/search")
# async def web_search(
#         engine: str = Query(..., description="exa, serper, or a prioritized list like exa|serper"),
#         q: str | None = Query(None),
#         query: str | None = Query(None),
#         data: bool = Query(False),
#         top_n: int = Query(3, ge=1, le=10),
#         user_id: str | None = Query(None),
# ):
#     """
#     Examples:
#       POST /api/v1/web/search?engine=exa&q=llm+observability
#       POST /api/v1/web/search?engine=exa|serper&q=ray+serve&data=true&top_n=2&user_id=demo
#       POST /api/v1/web/search?engine=serper,exa&query=python%20asyncio&data=true
#     """
#     t0 = time.perf_counter()
#     uid = (user_id or "anonymous").strip()
#     ensure_user(uid, None)
#
#     qtxt = _pick_query(q, query)
#     engines = _parse_engines(engine)
#
#     attempt_errors: list[dict] = []
#     results: list[dict] = []
#     scrape_logs: list[dict] = []
#     engine_used: str | None = None
#
#     for eng in engines:
#         try:
#             if eng == "exa":
#                 results = await _exa_search(qtxt, top_n, include_text=data)
#                 engine_used = "exa"
#             elif eng == "serper":
#                 results = await _serper_search(qtxt, top_n)
#                 engine_used = "serper"
#                 if data:
#                     results, scrape_logs = await _maybe_scrape(results, top_n=top_n)
#             break  # success → stop
#         except Exception as e:
#             attempt_errors.append({"engine": eng, "error": str(e)})
#
#     latency_ms = int((time.perf_counter() - t0) * 1000)
#
#     if engine_used is None:
#         event_id = log_api_event(
#             user_id=uid, api="/api/v1/web/search",
#             request_obj={"engines": engines, "q": qtxt, "data": data, "top_n": top_n, "user_id": uid},
#             response_obj={"errors": attempt_errors},
#             status="error", latency_ms=latency_ms, notes="all engines failed",
#         )
#         raise HTTPException(
#             status_code=502,
#             detail={"message": "All engines failed", "attempts": attempt_errors, "event_id": event_id},
#         )
#
#     response_summary = {
#         "engine_used": engine_used,
#         "attempted_engines": engines,
#         "results_count": len(results),
#         "scraped": int(bool(data)),
#         "first_error": attempt_errors[0] if attempt_errors else None,
#     }
#     event_id = log_api_event(
#         user_id=uid, api="/api/v1/web/search",
#         request_obj={"engines": engines, "q": qtxt, "data": data, "top_n": top_n, "user_id": uid},
#         response_obj=response_summary, status="ok", latency_ms=latency_ms,
#         notes="fallback_ok" if attempt_errors else None,
#     )
#     log_web_results(event_id, results)
#     if data and scrape_logs:
#         log_web_fetches(event_id, scrape_logs)
#
#     return {
#         "engine": engine_used,
#         "attempted_engines": engines,
#         "q": qtxt,
#         "data": data,
#         "top_n": top_n,
#         "results": results,
#         "event_id": event_id,
#         "attempt_errors": attempt_errors,
#     }
#
#
#
#
#
# from fastapi import UploadFile, File
# from fastapi import APIRouter
#
# @app.post("/api/v1/upload-files")
# async def upload_files(files: List[UploadFile] = File(...)):
#     upload_dir = "uploaded_files"
#     os.makedirs(upload_dir, exist_ok=True)
#     file_paths = []
#
#     for file in files:
#         file_path = os.path.join(upload_dir, file.filename)
#         with open(file_path, "wb") as f:
#             f.write(await file.read())
#         file_paths.append(file_path)
#     # Index all newly uploaded files at once
#     state = {
#         "mode": "incremental",
#         "roots": file_paths,
#         "model": None,
#         "force_reembed": True,
#         "stats": {}, "errors": []
#     }
#     cfg = _lg_config(thread_id=f"index:{int(time.time() * 1000)}", run_id="batch-upload")
#     result = await app.state.index_graph.ainvoke(state, config=cfg)
#     return {
#         "detail": f"{len(file_paths)} files uploaded and indexed",
#         "files": file_paths,
#         "stats": result.get("stats")
#     }
#
#
#
# @app.post("/api/v1/search/all")
# async def search_all(
#     search_req: SearchRequest,
#     web_engine: str = Query("serper|exa"),
#     web_top_n: int = Query(3)
# ):
#     # 1. Local file search (as before)
#     local_search_coro = search(search_req)  # your /api/v1/file/search logic
#
#     # 2. Web search
#     async def web_search_with_wrap():
#         return await web_search(
#             engine=web_engine,
#             q=search_req.query,
#             data=False,
#             top_n=web_top_n,
#             user_id=search_req.user_id
#         )
#     # Run both in parallel
#     local_result, web_result = await asyncio.gather(local_search_coro, web_search_with_wrap())
#
#     # Compose and return both
#     return {
#         "local_results": local_result.get("hits", []),
#         "web_results": web_result.get("results", []),
#         "local_latency_ms": local_result.get("latency_ms"),
#         "web_latency_ms": web_result.get("event_id"),  # or latency, as per your data
#     }
