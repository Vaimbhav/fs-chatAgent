

# local-agent

Lightweight local RAG (retrieval-augmented generation) agent built on FastAPI, LangGraph, SQLite, and Chroma.

This package provides:

* an HTTP API (FastAPI) to index, search and upload documents
* integrations with LangGraph for index/query graphs and checkpoints
* a ChromaDB-backed vector store for embeddings
* simple SQLite logging for queries and events

## Quick start (TL;DR)

**Prereqs:** Python >= 3.11, git

1. Create a virtualenv and install the package in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

2. Copy example env and edit keys/paths:

```bash
cp .env.example .env
# edit .env: OPENAI_API_KEY, INDEX_ROOTS, DATA_DIR, etc.
```

3. Run the API (either using the included `uv` tool if you installed it, or plain `uvicorn`)

**Using `uv` (optional helper defined in pyproject):**

```bash
# if you installed the `uv` CLI via the project tooling
uv run uvicorn agent_app.main:app --reload --host 0.0.0.0 --port 8000
```

**Or with plain uvicorn:**

```bash
python -m uvicorn agent_app.main:app --reload --host 0.0.0.0 --port 8000
```

Open API docs at: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Requirements & install

* Python 3.11 or newer (pyproject declares requires-python >=3.11)
* Install dependencies via pip (see pyproject.toml for pinned libs)

Install for development:

```bash
python -m pip install -e .[test]
```

If you prefer to avoid editable installs, use `pip install .` instead.

## Environment variables

Copy `.env.example` to `.env` and set the following at minimum:

* **OPENAI_API_KEY** — if you use OpenAI models
* **INDEX_ROOTS** — JSON-like list of paths to index (e.g. `INDEX_ROOTS=["./content"]`)
* **DATA_DIR / CHROMA_DIR / CHECKPOINT_DIR** — optional override of on-disk storage

The repository includes `.env.example` with common defaults.

## Usage

**Key API endpoints (all under `/api/v1`):**

* `POST /index-full` — full reindex (mode: full). Use `roots` in body to override `INDEX_ROOTS`.
* `POST /index` — incremental index of changed files.
* `POST /file/search` — local file search (JSON body: user_id, query, top_k).
* `GET /web/search` — web search using configured web engines (exa, serper).
* `POST /upload-files` — upload & index files via multipart upload.

**Health check:**
`GET /api/v1/health`

Example: index everything using the configured `INDEX_ROOTS`:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/index-full" -H "Content-Type: application/json" -d '{}'
```

## Tests

Run the pytest suite (project includes tests in `tests/`):

```bash
pytest -q
```

Run a single test file:

```bash
pytest tests/test_readers_formats.py::test_pdf_reader -q
```

## Data and persistence

* **Chroma persistence directory (default):** `./data/chroma`
* **LangGraph checkpoints and SQLite files:** under `./data` (`CHECKPOINT_DIR`)
* Fast, local testing uses the `checkpoint` SQLite checkpointers declared in `pyproject` via LangGraph

If you need to clear state, stop the server and remove the `./data` directory (or specific subfolders). Be careful: this deletes indexed data.

## Development notes

* **Main application entry:** `src/agent_app/main.py` (FastAPI app object: `app`)
* **Config:** `src/agent_app/config.py` — reads `.env` and exposes `SETTINGS`
* **Indexing/Query graphs:** `src/agent_app/graphs/` (LangGraph graph builders)
* **Vectorstore helpers:** `src/agent_app/vectorstore.py`

If you implement new readers or change indexing behavior, add tests under `tests/` and run the suite.

## Troubleshooting

* If uvicorn fails to start, ensure required native packages are installed and Python version matches (>=3.11).
* If embeddings fail, check `OPENAI_API_KEY` or other embedding provider keys in `.env`.
* If Chroma fails to start, inspect `CHROMA_DIR` and file permissions.

## Contributing

1. Fork the repo and create a branch.
2. Add tests for new behavior.
3. Run `pytest` and ensure green.
4. Open a pull request describing your changes.