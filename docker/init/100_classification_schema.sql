DO
$classification_schema$
DECLARE
  schema_name   text := 'classification';
  schema_owner  text := 'ddl_owner';
  rw_role       text := 'metadata_rw';
  ro_role       text := 'metadata_ro';
  alembic_role  text := 'metis_alembic_user';
BEGIN
  EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I AUTHORIZATION %I', schema_name, schema_owner);

  -- Current objects
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I, %I', schema_name, rw_role, ro_role);
  EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO %I', schema_name, rw_role);
  EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO %I', schema_name, ro_role);
  EXECUTE format('GRANT USAGE ON ALL SEQUENCES IN SCHEMA %I TO %I', schema_name, rw_role);
  EXECUTE format('GRANT USAGE ON ALL SEQUENCES IN SCHEMA %I TO %I', schema_name, ro_role);

  -- Future objects owned by alembic role
  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    alembic_role, schema_name, rw_role
  );
  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT ON TABLES TO %I',
    alembic_role, schema_name, ro_role
  );
  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT USAGE ON SEQUENCES TO %I',
    alembic_role, schema_name, rw_role
  );
  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT USAGE ON SEQUENCES TO %I',
    alembic_role, schema_name, ro_role
  );
END
$classification_schema$;
