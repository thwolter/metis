
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
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'embedding_rw') THEN
    EXECUTE 'CREATE ROLE embedding_rw NOLOGIN';
  END IF;
END$$;
