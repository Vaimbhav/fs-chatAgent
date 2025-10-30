from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    create_engine, Table, Column, Integer, String, Text, Float, Boolean,
    MetaData, ForeignKey, select
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text as sqla_text

from agent_app.config import SETTINGS
from pathlib import Path
import json

# Ensure parent dir exists
Path(SETTINGS.data_dir).mkdir(parents=True, exist_ok=True)

engine: Engine = create_engine(
    f"sqlite:///{SETTINGS.app_db_path}",
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
metadata = MetaData()

# --- Tables ---
users = Table(
    "users", metadata,
    Column("id", String, primary_key=True),
    Column("info_json", Text, nullable=True),
    Column("created_at", String, default=lambda: datetime.utcnow().isoformat())
)

files = Table(
    "files", metadata,
    Column("path", String, primary_key=True),
    Column("bytes", Integer),
    Column("mtime_ns", Integer),
    Column("sha256", String),
    Column("mime", String),
    Column("last_indexed_at", String),
)

queries = Table(
    "queries", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=False),
    Column("qtext", Text, nullable=False),
    Column("top_k", Integer, nullable=False),
    Column("filters_json", Text, nullable=True),
    Column("model", String, nullable=True),
    Column("latency_ms", Integer, nullable=True),
    Column("response_json", Text, nullable=True),
    Column("created_at", String, default=lambda: datetime.utcnow().isoformat()),
)

query_hits = Table(
    "query_hits", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("query_id", Integer, ForeignKey("queries.id", ondelete="CASCADE")),
    Column("rank", Integer, nullable=False),
    Column("score", Float, nullable=True),
    Column("path", String, nullable=True),
    Column("chunk_idx", Integer, nullable=True),
    Column("sha256", String, nullable=True),
    Column("snippet", Text, nullable=True),
)

api_events = Table(
    "api_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=True),
    Column("api", String, nullable=False),
    Column("request_json", Text, nullable=True),
    Column("response_json", Text, nullable=True),
    Column("status", String, nullable=False),  # ok | error
    Column("notes", Text, nullable=True),
    Column("latency_ms", Integer, nullable=True),
    Column("created_at", String, default=lambda: datetime.utcnow().isoformat()),
)

web_results = Table(
    "web_results", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", Integer, ForeignKey("api_events.id", ondelete="CASCADE")),
    Column("rank", Integer, nullable=False),
    Column("title", Text, nullable=True),
    Column("url", Text, nullable=True),
    Column("snippet", Text, nullable=True),
    Column("source", String, nullable=True),
    Column("published_date", String, nullable=True),
    Column("text_length", Integer, nullable=True),
)

web_fetches = Table(
    "web_fetches", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", Integer, ForeignKey("api_events.id", ondelete="CASCADE")),
    Column("url", Text, nullable=True),
    Column("ok", Boolean, nullable=True),
    Column("status", Integer, nullable=True),
    Column("length", Integer, nullable=True),
    Column("error", Text, nullable=True),
)

def init_db() -> None:
    metadata.create_all(engine)

def ensure_user(user_id: str, info: Optional[dict]) -> None:
    """Create user row if missing (uses Core select to satisfy IDE schema checks)."""
    with engine.begin() as conn:
        row = conn.execute(
            select(users.c.id).where(users.c.id == user_id)
        ).fetchone()
        if row is None:
            conn.execute(users.insert().values(
                id=user_id,
                info_json=json.dumps(info) if info else None,
                created_at=datetime.utcnow().isoformat()
            ))

def log_query_record(
    user_id: str,
    qtext: str,
    top_k: int,
    filters_json: Optional[str],
    model: Optional[str],
    latency_ms: Optional[int],
    response_json: Optional[str],
) -> int:
    with engine.begin() as conn:
        res = conn.execute(queries.insert().values(
            user_id=user_id, qtext=qtext, top_k=top_k, filters_json=filters_json,
            model=model, latency_ms=latency_ms, response_json=response_json,
            created_at=datetime.utcnow().isoformat()
        ))
        return int(res.inserted_primary_key[0])

def log_query_hits_records(query_id: int, hits: list[dict]) -> None:
    if not hits:
        return
    with engine.begin() as conn:
        for rank, h in enumerate(hits, start=1):
            meta = h.get("meta", {}) or {}
            conn.execute(query_hits.insert().values(
                query_id=query_id,
                rank=rank,
                score=float(h.get("score") or 0.0),
                path=meta.get("path"),
                chunk_idx=int(meta.get("chunk_idx") or 0),
                sha256=meta.get("sha256"),
                snippet=(h.get("text") or "")[:2000],
            ))

def log_api_event(
    user_id: str | None,
    api: str,
    request_obj: dict | None,
    response_obj: dict | None,
    status: str,
    latency_ms: int | None,
    notes: str | None = None,
) -> int:
    with engine.begin() as conn:
        res = conn.execute(api_events.insert().values(
            user_id=user_id,
            api=api,
            request_json=json.dumps(request_obj) if request_obj is not None else None,
            response_json=json.dumps(response_obj) if response_obj is not None else None,
            status=status,
            notes=notes,
            latency_ms=latency_ms,
            created_at=datetime.utcnow().isoformat(),
        ))
        return int(res.inserted_primary_key[0])

def log_web_results(event_id: int, results: list[dict]) -> None:
    if not results:
        return
    with engine.begin() as conn:
        for i, r in enumerate(results, start=1):
            conn.execute(web_results.insert().values(
                event_id=event_id,
                rank=i,
                title=r.get("title"),
                url=r.get("url"),
                snippet=r.get("snippet"),
                source=r.get("source"),
                published_date=r.get("publishedDate") or r.get("published_date"),
                text_length=r.get("text_length"),
            ))

def log_web_fetches(event_id: int, fetch_logs: list[dict]) -> None:
    if not fetch_logs:
        return
    with engine.begin() as conn:
        for log in fetch_logs:
            conn.execute(web_fetches.insert().values(
                event_id=event_id,
                url=log.get("url"),
                ok=bool(log.get("ok")),
                status=log.get("status"),
                length=log.get("length"),
                error=log.get("error"),
            ))
