\set ON_ERROR_STOP on

-- Create roles only if they do not already exist (idempotent)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vectra_rw') THEN
    CREATE ROLE vectra_rw NOLOGIN;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vectra_ro') THEN
    CREATE ROLE vectra_ro NOLOGIN;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'alembic_user') THEN
    CREATE ROLE alembic_user LOGIN PASSWORD 'alembic_password';
  END IF;
END $$;

-- Create extensions only if they do not already exist (already idempotent)
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
