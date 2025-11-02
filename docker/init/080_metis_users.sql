DO
$metis_users$
DECLARE
    app_user         text := 'metis_app_user';
    app_password     text := 'app-user-password';
    alembic_user     text := 'metis_alembic_user';
    alembic_password text := 'alembic-user-password';
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_user) THEN
        EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', app_user, app_password);
    ELSE
        EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', app_user, app_password);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = alembic_user) THEN
        EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', alembic_user, alembic_password);
    ELSE
        EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', alembic_user, alembic_password);
    END IF;

    EXECUTE format('GRANT metadata_rw TO %I', app_user);
    EXECUTE format('GRANT ddl_owner TO %I', alembic_user);
END
$metis_users$;
