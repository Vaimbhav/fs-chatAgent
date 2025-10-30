from __future__ import annotations
import os, json
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Load .env like your earlier version
load_dotenv()

def _parse_paths(val: str | None) -> list[str]:
    """Accepts JSON list (['/a','/b']) or comma-separated (/a,/b)."""
    if not val:
        return []
    v = val.strip()
    if v.startswith("["):
        try:
            return [str(p) for p in json.loads(v)]
        except Exception:
            pass
    return [p.strip() for p in v.split(",") if p.strip()]

# Canonical set of indexable extensions (used by readers)
INDEX_EXTS = {
    ".txt", ".md",
    ".pdf",
    ".doc", ".docx",
    ".ppt", ".pptx",
    ".xls", ".xlsx", ".csv",
    ".json", ".xml", ".html", ".htm",
}

@dataclass(frozen=True)
class Settings:
    # storage dirs
    data_dir: str = os.getenv("DATA_DIR", "./data")
    chroma_dir: str = os.getenv("CHROMA_DIR", "./data/chroma")
    checkpoint_dir: str = os.getenv("CHECKPOINT_DIR", "./data/checkpoints")

    # SQLite paths — keep both for compatibility
    sqlite_path: str = os.path.join(os.getenv("DATA_DIR", "./data"), "app.sqlite")
    app_db_path: str = os.getenv("APP_DB_PATH") or os.path.join(os.getenv("DATA_DIR", "./data"), "app.sqlite")

    # embeddings / OpenAI
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    # default roots
    default_roots: tuple[str, ...] = tuple(_parse_paths(os.getenv("INDEX_ROOTS")))

SETTINGS = Settings()

# Ensure directories exist (keeps behavior from your recent version)
Path(SETTINGS.data_dir).expanduser().mkdir(parents=True, exist_ok=True)
Path(SETTINGS.chroma_dir).expanduser().mkdir(parents=True, exist_ok=True)
Path(SETTINGS.checkpoint_dir).expanduser().mkdir(parents=True, exist_ok=True)







#
# from __future__ import annotations
# import os, json
# from dataclasses import dataclass
# from pathlib import Path
# from typing import List
#
# def _parse_roots(val: str | None) -> List[str]:
#     if not val:
#         return []
#     s = val.strip()
#     if s.startswith("["):
#         try:
#             arr = json.loads(s)
#             return [str(Path(p).expanduser()) for p in arr]
#         except Exception:
#             pass
#     return [str(Path(p).expanduser()) for p in s.split(",") if p.strip()]
#
# # Canonical set of indexable extensions (readers.py imports this)
# INDEX_EXTS = {
#     ".txt", ".md",
#     ".pdf",
#     ".doc", ".docx",
#     ".ppt", ".pptx",
#     ".xls", ".xlsx", ".csv",
#     ".json", ".xml", ".html", ".htm",
# }
#
# @dataclass(frozen=True)
# class _Settings:
#     data_dir: str
#     chroma_dir: str
#     checkpoint_dir: str
#     default_roots: List[str]
#     embedding_model: str
#     openai_api_key: str
#     app_db_path: str
#
# def _load() -> _Settings:
#     data_dir = os.getenv("DATA_DIR", "./data")
#     chroma_dir = os.getenv("CHROMA_DIR", f"{data_dir}/chroma")
#     checkpoint_dir = os.getenv("CHECKPOINT_DIR", f"{data_dir}/checkpoints")
#     default_roots = _parse_roots(os.getenv("INDEX_ROOTS")) or []
#     embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
#     openai_api_key = os.getenv("OPENAI_API_KEY", "")
#     app_db_path = os.getenv("APP_DB_PATH", f"{data_dir}/app.sqlite")
#
#     Path(data_dir).expanduser().mkdir(parents=True, exist_ok=True)
#     Path(chroma_dir).expanduser().mkdir(parents=True, exist_ok=True)
#     Path(checkpoint_dir).expanduser().mkdir(parents=True, exist_ok=True)
#
#     return _Settings(
#         data_dir=str(Path(data_dir).expanduser()),
#         chroma_dir=str(Path(chroma_dir).expanduser()),
#         checkpoint_dir=str(Path(checkpoint_dir).expanduser()),
#         default_roots=[str(Path(p).expanduser()) for p in default_roots],
#         embedding_model=embedding_model,
#         openai_api_key=openai_api_key,
#         app_db_path=str(Path(app_db_path).expanduser()),
#     )
#
# SETTINGS = _load()
