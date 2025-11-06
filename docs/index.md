# FDE Classifier Documentation

Metis ingests document jobs, extracts structured metadata with LangGraph agents,
and persists results with tenant-aware row-level security. Use this guide to
navigate the platform’s architecture, domain-specific workflows, and APIs.

## Docs Map

- **Architecture & Operations** – FastAPI app, Dramatiq workers, pgvector storage,
  and TenAuth-backed RBAC form the backbone of the service.
- **Domain Guides** – deep dives on core packages such as
  [Classification Pipeline](classification/index.md).
- **API Reference** – detailed request/response schema for all `/v1` endpoints in
  the [Metadata API Reference](frontend_api_spec.md).

## Getting Started

1. Export dummy `OPENAI_API_KEY`/`TAVILY_API_KEY` and configure PostgreSQL connection strings.
2. Apply the latest migrations: `alembic upgrade head`.
3. Launch the API: `./.venv/bin/python main.py`.

## Documentation Tooling

```bash
uv run mkdocs serve
```

Start a preview at <http://127.0.0.1:8000>. Build static assets with `uv run mkdocs build`
to populate the `site/` directory.
