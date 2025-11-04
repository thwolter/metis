DO $$
DECLARE
  db_name text := current_database();
BEGIN
  EXECUTE format(
    'ALTER ROLE %I IN DATABASE %I SET search_path = classification, metadata, public',
    'metis_app_user',
    db_name
  );
  EXECUTE format(
    'ALTER ROLE %I IN DATABASE %I SET search_path = classification, metadata, public',
    'metis_alembic_user',
    db_name
  );
END$$;
