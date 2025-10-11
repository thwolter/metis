# Repository Guidelines

## Project Structure & Module Organization
- `src/` holds application code split into domains such as `agent/`, `metadata/`, and `core/`. Each package exposes Pydantic schemas, SQLModel models, and service utilities.
- `alembic/` contains database migrations (`versions/`) and Alembic configuration. The migrations target the `metadata` schema; keep new revisions scoped accordingly.
- `tests/` is organized by level (`unit_tests/`, `integration_tests/`) and mirrors the `src/` layout for ease of discovery.
- `notebooks/` and `agent.egg-info/` are ancillary; avoid coupling production logic to them.

## Build, Test, and Development Commands
- `uv run task lint` (if defined) or `./.venv/bin/ruff check src tests` validates lint rules.
- `./.venv/bin/python -m pytest -q` runs the full test suite. Export `OPENAI_API_KEY` and `TAVILY_API_KEY` with dummy values when offline.
- `alembic upgrade head` applies migrations using the DSN in `.env.migration` (`ALEMBIC_DATABASE_URL`). Run from the repository root.
- `./.venv/bin/python main.py` launches the FastAPI entrypoint for manual smoke checks.

## Coding Style & Naming Conventions
- Python code uses 4-space indentation and follows Ruff’s defaults (`pyproject.toml` sets line length 120, single quotes).
- SQLModel classes should keep enum-backed states (`JobStatus`) and serialize JSON fields via `model_dump(mode='json')`.
- Module names remain lowercase with underscores (`metadata/service.py`), while Pydantic models and SQLModels use `PascalCase`.

## Testing Guidelines
- Prefer `tests/unit_tests/` for pure logic and `tests/integration_tests/` when invoking agents or database layers.
- Name tests descriptively (`test_<behavior>_<expectation>`), mirroring the target module.
- Use the in-memory SQLite fixtures provided in `tests/test_metadata_service.py`; avoid hard-coded Postgres dependencies in unit tests.

## Commit & Pull Request Guidelines
- Follow Conventional Commits (`feat:`, `fix:`, etc.); the repo ships with Commitizen (`cz`) and will lint on release bumps.
- PRs should include: summary of user impact, references to issue IDs, screenshots or logs for API/UI changes, and confirmation that `pytest` and `ruff` have been run.

## Security & Configuration Tips
- `.env` drives application settings via `core.config.get_settings`; never commit real keys.
- Observability flags (`OTLP_ENDPOINT`, `OTLP_HEADERS`, `OTEL_LOGS_ENABLED`) live in `.env`; unset or disable them locally when exporters are unavailable.
- Alembic reads `.env.migration`—ensure the file contains only migration-safe credentials and switch to temporary secrets for review apps.
