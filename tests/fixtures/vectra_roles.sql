
CREATE ROLE vectra_rw NOLOGIN;
CREATE ROLE vectra_ro NOLOGIN;
CREATE ROLE alembic_user LOGIN PASSWORD 'alembic_password';

CREATE EXTENSION pgcrypto;
CREATE EXTENSION vector;
