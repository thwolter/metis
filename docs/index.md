# FDE Classifier Documentation

Welcome to the FDE Classifier documentation site. This project ingests document jobs,
extracts structured metadata with LangGraph agents, and persists results with tenant-aware
row-level security.

## What You'll Find

- **Architecture Overview** – how FastAPI, Dramatiq workers, and PGVector collaborate.
- **Authentication Flow** – requests use `Authorization: Bearer <jwt>`; tenancy comes from the `tid` claim.
- **Metadata API Reference** – detailed request/response schema for all `/v1` endpoints.

## Getting Started

1. Export dummy `OPENAI_API_KEY`/`TAVILY_API_KEY` and configure PostgreSQL connection strings.
2. Apply the latest migrations: `alembic upgrade head`.
3. Launch the API: `./.venv/bin/python main.py`.

## Building the Docs

```bash
uv run mkdocs serve
```

This starts a local preview at <http://127.0.0.1:8000>. Use `mkdocs build` to generate static
site assets under `site/`.
