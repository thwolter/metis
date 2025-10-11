# Repository Guidelines

## Project Structure & Module Organization
- `src/main.py` provides the FastAPI entry point and wires the app, queues, and settings together.
- `src/core/` hosts shared infrastructure (config loading, database session management, Dramatiq broker utilities, tenancy helpers).
- `src/metadata/` contains the primary domain logic: Pydantic schemas, SQLModel models, service layer, async tasks, and API routes.
- `src/agent/` captures LangGraph agent logic (graph orchestration, nodes, tools, and state handling).
- `src/utils/` stores cross-cutting helpers; keep these focused and dependency-light.
- `alembic/` tracks migrations; `tests/` is split into `unit_tests/` and `integration_tests/` to encourage layering.

## Build, Test, and Development Commands
- `uv sync` installs runtime and `dev` dependencies from `pyproject.toml`/`uv.lock`.
- `uv run uvicorn main:app --reload` runs the API locally with auto-reload (ensure Redis/Postgres services are reachable).
- `uv run alembic upgrade head` applies migrations; run this before starting workers or the API.
- `uv run dramatiq metadata.tasks:broker -p 1 -t 8` starts the Dramatiq worker matching the Docker entrypoint defaults.
- `uv run pytest` executes the full test suite; add `tests/unit_tests` or `tests/integration_tests` to scope runs.
- Optional: `docker build -t classifier .` produces the production image used by CI/CD or deployment scripts.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and type hints on public functions.
- Domain modules (`metadata`, `agent`) use snake_case filenames and PascalCase Pydantic/SQLModel classes; keep request/response schemas in `schemas.py`.
- Format with `uv run ruff format` and lint with `uv run ruff check`; fix import ordering via `uv run isort .` and symbol sorting via `uv run ssort src`.
- Prefer stdlib `logging` with the OpenTelemetry handler configured in `core/logging.py`, and limit cross-module side effects to keep agent graph execution predictable.

## Testing Guidelines
- Unit tests live in `tests/unit_tests/test_*.py`; integration flows reside in `tests/integration_tests/`.
- Structure tests around public APIs (services, FastAPI routes, Dramatiq tasks) and isolate external calls with fakes or fixtures (see `tests/conftest.py`).
- Use `pytest.mark.asyncio` for coroutine tests and ensure new async helpers include awaited assertions.
- When adding features, include both unit coverage for edge cases and at least one integration path validating orchestrated workflows.

## Commit & Pull Request Guidelines
- The repo is configured for Conventional Commits (`[tool.commitizen]`); prefer `uv run cz commit` to keep messages consistent (`feat:`, `fix:`, `refactor:`).
- Keep subject lines imperative and under 72 characters; add concise body bullets if context is required.
- Before opening a PR, run linting, formatting, migrations (if relevant), and the full test suite; attach command output in the PR description.
- Reference related issues, call out schema or migration impacts, and provide API payload examples or screenshots when behavior changes.
- Ensure PRs describe agent workflow adjustments (graph topology, new nodes/tools) so reviewers can verify LangGraph impacts quickly.
