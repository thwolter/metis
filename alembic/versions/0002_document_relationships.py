"""Introduce documents table and cascading relationships."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '0002_document_relationships'
down_revision = '0001_initial_with_rls'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'documents',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'created_at',
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
        sa.PrimaryKeyConstraint('tenant_id', 'document_id'),
        schema='metadata',
    )

    op.execute(
        """
        INSERT INTO metadata.documents (tenant_id, document_id)
        SELECT DISTINCT tenant_id, document_id FROM metadata.metadata_jobs
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO metadata.documents (tenant_id, document_id)
        SELECT DISTINCT tenant_id, document_id FROM metadata.document_metadata
        ON CONFLICT DO NOTHING
        """
    )

    op.create_foreign_key(
        'fk_jobs_document',
        'metadata_jobs',
        'documents',
        ['tenant_id', 'document_id'],
        ['tenant_id', 'document_id'],
        source_schema='metadata',
        referent_schema='metadata',
        ondelete='CASCADE',
    )

    op.create_foreign_key(
        'fk_document_metadata_document',
        'document_metadata',
        'documents',
        ['tenant_id', 'document_id'],
        ['tenant_id', 'document_id'],
        source_schema='metadata',
        referent_schema='metadata',
        ondelete='CASCADE',
    )

    op.execute('ALTER TABLE metadata.documents ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE metadata.documents FORCE ROW LEVEL SECURITY;')
    op.execute(
        """
        CREATE POLICY documents_tenant_policy
        ON metadata.documents
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.drop_constraint('fk_document_metadata_document', 'document_metadata', schema='metadata', type_='foreignkey')
    op.drop_constraint('fk_jobs_document', 'metadata_jobs', schema='metadata', type_='foreignkey')

    op.execute('DROP POLICY IF EXISTS documents_tenant_policy ON metadata.documents;')
    op.execute('ALTER TABLE metadata.documents DISABLE ROW LEVEL SECURITY;')

    op.drop_table('documents', schema='metadata')
