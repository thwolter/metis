\set ON_ERROR_STOP on

-- Ensure the service role exists (idempotent)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'classifier_service') THEN
    CREATE ROLE classifier_service NOINHERIT;
  END IF;
END $$;

-- Grant role to the test app user if it exists
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'metis_app_user') THEN
    GRANT classifier_service TO metis_app_user;
  END IF;
END $$;

-- Schema usage (only if schemas exist in the test DB at this moment)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'vectra') THEN
    GRANT USAGE ON SCHEMA vectra TO classifier_service;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'metadata') THEN
    GRANT USAGE ON SCHEMA metadata TO classifier_service;
  END IF;
END $$;

-- Apply/select policies for any embeddings table that now exists
DO $$
BEGIN
  IF to_regclass('vectra.langchain_pg_embedding') IS NOT NULL THEN
    ALTER TABLE vectra.langchain_pg_embedding ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS svc_all_select ON vectra.langchain_pg_embedding;
    CREATE POLICY svc_all_select
      ON vectra.langchain_pg_embedding
      FOR SELECT
      TO classifier_service
      USING (TRUE);
    GRANT SELECT ON vectra.langchain_pg_embedding TO classifier_service;
  END IF;
END $$;

-- Optional: documents (some tests may not create it yet)
DO $$
BEGIN
  IF to_regclass('metadata.documents') IS NOT NULL THEN
    ALTER TABLE metadata.documents ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS svc_all_select ON metadata.documents;
    CREATE POLICY svc_all_select
      ON metadata.documents
      FOR SELECT
      TO classifier_service
      USING (TRUE);
    GRANT SELECT ON metadata.documents TO classifier_service;
  END IF;
END $$;

-- Repeat blocks for any additional tables a test might create on-demand.
