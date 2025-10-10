# syntax=docker/dockerfile:1.7

# Base image
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Ensure venv on PATH
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# Install system dependencies (libpq for psycopg2, build essentials) in a single layer
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       libpq-dev \
       curl \
       ca-certificates \
    && python -m venv "$VIRTUAL_ENV" \
    && pip install --upgrade pip setuptools wheel \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Leverage Docker layer caching where possible
COPY pyproject.toml uv.lock* ./

# Copy source before install so `pip install .` can find packages
COPY src ./src

# Install project runtime deps and uvicorn (server)
# Note: uvicorn is used to serve FastAPI and is not declared in project deps
RUN pip install "uvicorn[standard]>=0.34.0" \
    && pip install .

# Copy Alembic files
COPY alembic.ini ./
COPY alembic ./alembic
# Note: do not bake secrets or env files into the image; provide ALEMBIC_DATABASE_URL at runtime

# Copy entrypoint script
COPY scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh
RUN chmod +x ./scripts/docker-entrypoint.sh

# Expose API port
EXPOSE 8000

# Environment defaults (can be overridden at runtime)
ENV PYTHONPATH=/app/src \
    HOST=0.0.0.0 \
    PORT=8000

# The entrypoint runs migrations, then starts Dramatiq and Uvicorn
ENTRYPOINT ["./scripts/docker-entrypoint.sh"]
