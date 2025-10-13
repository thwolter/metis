# Metis

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://pre-commit.com/)
[![Ruff](https://img.shields.io/badge/lint-Ruff-0C55A7?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![isort](https://img.shields.io/badge/imports-isort-ef8336?logo=python&logoColor=white)](https://pycqa.github.io/isort/)
[![ssort](https://img.shields.io/badge/structuring-ssort-5C2D91)](https://github.com/bwhmather/ssort)
[![Commitizen](https://img.shields.io/badge/commits-Commitizen-brightgreen?logo=git&logoColor=white)](https://commitizen-tools.github.io/commitizen/)
[![gitleaks](https://img.shields.io/badge/secrets-gitleaks-orange?logo=gitlab&logoColor=white)](https://github.com/gitleaks/gitleaks)
[![Pyrefly](https://img.shields.io/badge/type%20checks-Pyrefly-6236FF)](https://github.com/facebookresearch/pyrefly)

Metis is a FastAPI service that orchestrates document metadata extraction and classification for multi-tenant workloads. The service coordinates asynchronous agents, versioned storage, and vector-store enrichment to keep document catalogues searchable and trustworthy.

## Features
- FastAPI metadata API secured with TenAuth JWTs and multi-tenant session scoping.
- Asynchronous Dramatiq workers to run LangGraph agents and persist results without blocking clients.
- Versioned metadata store built on SQLModel + PostgreSQL/pgvector with fingerprinted payloads and manual override support.
- Vector store synchronisation that updates LangChain PostgreSQL embeddings alongside metadata revisions.
- Observability hooks for OTLP traces/logs and structured logging across API and worker processes.

## Architecture
- Application: `src/main.py` boots the FastAPI app, health probes, and routes under `/v1`.
- Metadata domain: `src/metadata/` provides DTOs, SQLModel models, REST endpoints, and job orchestration helpers.
- Agents: `src/agent/` defines the LangGraph pipeline that classifies documents and emits `MetadataSchema`.
- Queueing: `src/core/queueing.py` wires Dramatiq to Redis; workers in `metadata/tasks.py` consume jobs.
- Persistence: PostgreSQL + pgvector stores metadata versions (`metadata/models.py`) and LangChain collections.
- Security: TenAuth access context middleware injects tenant/user IDs into every DB session.

## Getting Started
1. Install tooling (Python 3.12+, [uv](https://docs.astral.sh/uv/), Redis, PostgreSQL with the pgvector extension).
2. Synchronise dependencies and create the virtualenv:
   ```bash
   uv sync
   ```
3. Configure environment variables in `.env` (see `src/core/config.py` for the full list). At minimum set:
   - `POSTGRES_URL` and `REDIS_URL`
   - `OPENAI_API_KEY` and `TAVILY_API_KEY` (dummy values are fine for local tests)
   - `ALEMBIC_DATABASE_URL` in `.env.migration` for migrations
4. Bootstrap the database schema:
   ```bash
   uv run alembic upgrade head
   ```
5. Launch the API (reload optional for local development):
   ```bash
   uv run uvicorn src.main:app --reload
   ```
6. Start a Dramatiq worker so background jobs are processed:
   ```bash
   uv run dramatiq metadata.tasks --queues default --processes 1
   ```

Health checks are available at `/healthz` and `/readyz`. All `/v1/**` routes require `Authorization: Bearer <jwt>` tokens that include `tid` and `sub` claims.

## API Quick Tour
- `POST /v1/metadata`: enqueue metadata extraction for a document, optionally waiting for completion.
- `POST /v1/documents/{document_id}/rebuild`: rebuild metadata using the latest ingestion context.
- `GET /v1/jobs/{job_id}` / `DELETE /v1/jobs/{job_id}`: inspect or cancel queued jobs.
- `GET /v1/documents/{document_id}/metadata?version=latest|vN`: fetch versioned metadata snapshots.
- `PUT /v1/documents/{document_id}/metadata`: persist manual overrides without invoking the agent.

Requests automatically capture tenant/user context, merge generated metadata with locked fields, and update the vector store when jobs succeed.

## Quality Gates
- `uv run task lint` (or `./.venv/bin/ruff check src tests`) runs Ruff lint and formatting.
- `./.venv/bin/python -m pytest -q` executes the full test suite (seed `OPENAI_API_KEY`/`TAVILY_API_KEY` if offline).
- `pre-commit install` followed by `pre-commit run --all-files` enforces formatting, import sorting (`isort`/`ssort`), Ruff lint/format, `gitleaks`, Commitizen policy, and Pyrefly type checks.
- Use `cz commit` for Conventional Commit messages; `cz check` validates history before release.

## Documentation
MkDocs powers the user guide in `docs/`.
- Develop locally with `uv run mkdocs serve`
- Produce static assets with `uv run mkdocs build` (output in `site/`)

## Observability
Set `OTLP_ENDPOINT`, `OTLP_HEADERS`, `OTEL_LOGS_ENABLED`, and related flags in `.env` to forward traces/logs. Logging is structured via `core.logging.configure_logging()`; adjust `LOG_LEVEL`/`log_level` as needed.

## Contributing
- Run the quality gates above before pushing.
- Keep migrations scoped to the `metadata` schema (`alembic/versions`).
- Follow the repository conventions in `AGENTS.md` and `CHANGELOG.md`.

## License
Distributed under the MIT License. See `LICENSE` for details.
