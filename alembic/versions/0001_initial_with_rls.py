"""Initial metadata schema with tenant RLS."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '0001_initial_with_rls'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS metadata;')

    op.create_table(
        'metadata_jobs',
        sa.Column('job_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('profile', sa.Text(), nullable=False),
        sa.Column('ingestion_fingerprint', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='queued'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('retries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_type', sa.Text(), nullable=True),
        sa.Column('error_msg', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=False), nullable=False),
        sa.Column('started_at', sa.TIMESTAMP(timezone=False), nullable=True),
        sa.Column('finished_at', sa.TIMESTAMP(timezone=False), nullable=True),
        sa.Column('processing_fingerprint', sa.Text(), nullable=True),
        sa.Column('callback_url', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.Text(), nullable=True),
        sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('input_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('locked_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.UniqueConstraint(
            'tenant_id',
            'document_id',
            'profile',
            'ingestion_fingerprint',
            name='uq_job_idempotency',
        ),
        schema='metadata',
    )

    op.create_index(
        'ix_jobs_status_priority_created',
        'metadata_jobs',
        ['status', 'priority', 'created_at'],
        schema='metadata',
    )
    op.create_index(
        'ix_jobs_tenant_created',
        'metadata_jobs',
        ['tenant_id', 'created_at'],
        schema='metadata',
    )

    op.create_table(
        'document_metadata',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('fingerprint', sa.Text(), nullable=False),
        sa.Column('extracted_on', sa.TIMESTAMP(timezone=False), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('tenant_id', 'document_id', 'version'),
        schema='metadata',
    )

    op.create_index(
        'ix_docmeta_tenant_doc_version',
        'document_metadata',
        ['tenant_id', 'document_id', 'version'],
        unique=True,
        schema='metadata',
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'metadata_rw') THEN
                CREATE ROLE metadata_rw NOLOGIN;
            END IF;
        END
        $$;
        """
    )

    op.execute('GRANT USAGE ON SCHEMA metadata TO metadata_rw;')
    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA metadata TO metadata_rw;')
    op.execute(
        'ALTER DEFAULT PRIVILEGES IN SCHEMA metadata GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO metadata_rw;'
    )

    op.execute('ALTER TABLE metadata.metadata_jobs ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE metadata.metadata_jobs FORCE ROW LEVEL SECURITY;')
    op.execute(
        """
        CREATE POLICY metadata_jobs_tenant_policy
        ON metadata.metadata_jobs
        USING (tenant_id = current_setting('app.tenant_id', false)::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id', false)::uuid)
        """
    )

    op.execute('ALTER TABLE metadata.document_metadata ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE metadata.document_metadata FORCE ROW LEVEL SECURITY;')
    op.execute(
        """
        CREATE POLICY document_metadata_tenant_policy
        ON metadata.document_metadata
        USING (tenant_id = current_setting('app.tenant_id', false)::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id', false)::uuid)
        """
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS document_metadata_tenant_policy ON metadata.document_metadata;')
    op.execute('ALTER TABLE metadata.document_metadata DISABLE ROW LEVEL SECURITY;')
    op.execute('DROP INDEX IF EXISTS metadata.ix_docmeta_tenant_doc_version;')
    op.drop_table('document_metadata', schema='metadata')

    op.execute('DROP POLICY IF EXISTS metadata_jobs_tenant_policy ON metadata.metadata_jobs;')
    op.execute('ALTER TABLE metadata.metadata_jobs DISABLE ROW LEVEL SECURITY;')
    op.drop_index('ix_jobs_tenant_created', table_name='metadata_jobs', schema='metadata')
    op.drop_index('ix_jobs_status_priority_created', table_name='metadata_jobs', schema='metadata')
    op.drop_table('metadata_jobs', schema='metadata')

    op.execute('DROP SCHEMA IF EXISTS metadata CASCADE;')
