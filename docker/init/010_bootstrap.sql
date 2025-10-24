-- Create logical roles (no login)
\echo '=== Running bootstrap: creating roles and schema ==='

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ddl_owner') THEN
    CREATE ROLE ddl_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'metadata_rw') THEN
    CREATE ROLE metadata_rw NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'metadata_ro') THEN
    CREATE ROLE metadata_ro NOLOGIN;
  END IF;
END$$;

-- Create runtime and migration users
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'metis_app_user') THEN
    CREATE ROLE metis_app_user LOGIN PASSWORD 'app-user-password';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'metis_alembic_user') THEN
    CREATE ROLE metis_alembic_user LOGIN PASSWORD 'alembic-user-password';
  END IF;
END$$;

-- Memberships
GRANT metadata_rw TO metis_app_user;
GRANT ddl_owner TO metis_alembic_user;

-- Dedicated schema owned by ddl_owner
CREATE SCHEMA IF NOT EXISTS metadata AUTHORIZATION ddl_owner;

-- Baseline + default privileges so future objects are usable without Alembic issuing GRANTs
GRANT USAGE ON SCHEMA metadata TO metadata_rw, metadata_ro;

ALTER DEFAULT PRIVILEGES FOR ROLE metis_alembic_user IN SCHEMA metadata
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO metadata_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE metis_alembic_user IN SCHEMA metadata
  GRANT SELECT ON TABLES TO metadata_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE metis_alembic_user IN SCHEMA metadata
  GRANT USAGE, SELECT ON SEQUENCES TO metadata_rw, metadata_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE metis_alembic_user IN SCHEMA metadata
  GRANT EXECUTE ON FUNCTIONS TO metadata_rw, metadata_ro;

-- Ensure role connections default to the metadata schema
DO $$
DECLARE
  db_name text := current_database();
BEGIN
  EXECUTE format(
    'ALTER ROLE %I IN DATABASE %I SET search_path = metadata, public',
    'metis_app_user',
    db_name
  );
  EXECUTE format(
    'ALTER ROLE %I IN DATABASE %I SET search_path = metadata, public',
    'metis_alembic_user',
    db_name
  );
END$$;

-- Optional: enable pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

\echo '=== Bootstrap completed ==='
