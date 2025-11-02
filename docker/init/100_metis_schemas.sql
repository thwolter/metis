-- Manage the metadata schema and its default privileges in a single DO block
DO
$metadata_schema$
DECLARE
  schema_name text := 'metadata';
  schema_owner text := 'ddl_owner';
  rw_role text := 'metadata_rw';
  ro_role text := 'metadata_ro';
  alembic_role text := 'metis_alembic_user';
BEGIN
  EXECUTE format(
    'CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION %I',
    schema_name,
    schema_owner
  );

  EXECUTE format(
    'GRANT USAGE ON SCHEMA %I TO %I, %I',
    schema_name,
    rw_role,
    ro_role
  );

  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    alembic_role,
    schema_name,
    rw_role
  );

  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT ON TABLES TO %I',
    alembic_role,
    schema_name,
    ro_role
  );

  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT USAGE, SELECT ON SEQUENCES TO %I, %I',
    alembic_role,
    schema_name,
    rw_role,
    ro_role
  );

  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT EXECUTE ON FUNCTIONS TO %I, %I',
    alembic_role,
    schema_name,
    rw_role,
    ro_role
  );
END
$metadata_schema$;
