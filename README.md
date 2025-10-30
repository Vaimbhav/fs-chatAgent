# fs-chatAgent

Local research/chat agent (FastAPI + Chroma + Vite/React).

This repository contains a local RAG-style chat agent that indexes files on disk into a Chroma vector store and exposes a small API to query those documents. The project includes a TypeScript + React frontend (Vite) and a Python-based agent service in `local-agent/` that runs a FastAPI HTTP API and the indexing/query graphs.

## Key features

- Index local files (PDF, DOCX, PPTX, XLSX, text) into Chroma for semantic search
- Upload files via API and trigger on-demand indexing
- Unified search endpoints (local files + optional web search)
- Small Vite + React frontend for quick interactions

## Repository layout

- `local-agent/` — Python service (FastAPI) with indexing, vectorstore wiring, and LangGraph graphs
  - `pyproject.toml` — project metadata and dependencies
  - `src/agent_app/` — main application code (endpoints, graphs, readers)
- `frontend/` — Vite + React application used as a simple UI
- `data/` and `local-agent/data/` — sample checkpoints, persisted Chroma DB, upload folders (may be created at runtime)
- `tests/` — pytest tests for the Python service

## Prerequisites

- macOS / Linux / Windows
- Python 3.11+
- Node.js 18+ (or an LTS >=18)
- Recommended: a recent pip (or use a virtualenv)

## Quickstart — Python service (local-agent)

1. Create and activate a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install the local Python package in editable mode (this installs dependencies listed in `local-agent/pyproject.toml`).

```bash
pip install -e ./local-agent
# If you need dev/test deps, install pytest: pip install pytest
```

3. Run the FastAPI server (from repo root):

```bash
uvicorn agent_app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir ./local-agent/src
```

Notes:
- The FastAPI app package is located at `local-agent/src/agent_app`. Running `uvicorn agent_app.main:app` from the repo root requires `--app-dir ./local-agent/src` so Python finds the package.
- On startup the service will create checkpoint directories and wire up the Chroma collection files under the configured checkpoint path.

## Quickstart — Frontend

1. Install dependencies and run the dev server:

```bash
cd frontend
npm install
npm run dev
```

2. The Vite dev server defaults to `http://localhost:5173`. The frontend is configured to call the API on `http://localhost:8000` (see CORS settings in the Python app).

## Environment / configuration

Create a `.env` file (or export variables) for the Python service. Typical environment variables:

- `OPENAI_API_KEY` — (optional) API key used for embeddings/LLM provider
- `EXA_API_KEY`, `SERPER_API_KEY` — optional web-search provider keys
- `CHECKPOINT_DIR` — where to persist Chroma/SQLite checkpoints (defaults handled by `local-agent` settings)

See `local-agent/src/agent_app/config.py` for the full list of supported settings and defaults.

## Data and persistence

- Chroma persistence files are stored under whatever `CHECKPOINT_DIR` (or `local-agent/data/` by default) is configured.
- Uploaded files via the API are saved to an upload folder (see `local-agent/src/agent_app/main.py` upload endpoints) and indexed automatically.

## Tests

Run Python tests (from repo root):

```bash
pytest -q
```

The `tests/` directory contains unit/functional tests for the agent. Install `pytest` into your virtualenv if needed.

## Common commands

- Start backend: uvicorn agent_app.main:app --reload --app-dir ./local-agent/src
- Start frontend: (from `frontend/`) npm run dev
- Install Python package in editable mode: pip install -e ./local-agent
- Run tests: pytest

## Contributing

Contributions are welcome. A simple workflow:

1. Fork the repo and create a feature branch.
2. Run unit tests and linters locally.
3. Open a PR describing your change.

If you add or upgrade dependencies, update `local-agent/pyproject.toml` (or `frontend/package.json`) and document the change in this README or `CHANGELOG.md`.
