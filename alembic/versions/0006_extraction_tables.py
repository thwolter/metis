"""Create extraction job and attribute tables with RLS.

Revision ID: 0006_extraction_tables
Revises: 2c1f3e2c3f1a
Create Date: 2025-11-07 10:00:00

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = '0006_extraction_tables'
down_revision = '2c1f3e2c3f1a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'extraction_jobs',
        sa.Column('job_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('doc_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('doc_type', sa.String(length=128), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('model_version', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default=sa.text("'queued'")),
        sa.Column('document_digest', sa.String(length=128), nullable=False),
        sa.Column('collection_name', sa.String(length=255), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('seq', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('retriever_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint('tenant_id', 'doc_id', 'doc_type', name='uq_extraction_jobs_document'),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'doc_id'],
            ['metadata.documents.tenant_id', 'metadata.documents.document_id'],
            name='fk_extraction_jobs_document',
            ondelete='CASCADE',
        ),
        schema='metadata',
    )

    op.create_index(
        'ix_extraction_jobs_tenant_created',
        'extraction_jobs',
        ['tenant_id', 'created_at'],
        schema='metadata',
    )

    op.create_table(
        'extracted_attributes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('doc_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('attribute', sa.String(length=128), nullable=False),
        sa.Column('value_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column(
            'provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column('model_version', sa.String(length=64), nullable=False),
        sa.Column('constraints_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")
        ),
        sa.ForeignKeyConstraint(
            ['job_id'],
            ['metadata.extraction_jobs.job_id'],
            name='fk_extracted_attributes_job',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'doc_id'],
            ['metadata.documents.tenant_id', 'metadata.documents.document_id'],
            name='fk_extracted_attributes_document',
            ondelete='CASCADE',
        ),
        sa.UniqueConstraint('job_id', 'attribute', name='uq_extracted_attribute_job'),
        schema='metadata',
    )

    op.create_index(
        'ix_extracted_attributes_tenant_attribute',
        'extracted_attributes',
        ['tenant_id', 'attribute'],
        schema='metadata',
    )

    op.execute('ALTER TABLE metadata.extraction_jobs ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE metadata.extraction_jobs FORCE ROW LEVEL SECURITY;')
    op.execute(
        """
        CREATE POLICY extraction_jobs_tenant_policy
        ON metadata.extraction_jobs
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )

    op.execute('ALTER TABLE metadata.extracted_attributes ENABLE ROW LEVEL SECURITY;')
    op.execute('ALTER TABLE metadata.extracted_attributes FORCE ROW LEVEL SECURITY;')
    op.execute(
        """
        CREATE POLICY extracted_attributes_tenant_policy
        ON metadata.extracted_attributes
        USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS extracted_attributes_tenant_policy ON metadata.extracted_attributes;')
    op.execute('ALTER TABLE metadata.extracted_attributes DISABLE ROW LEVEL SECURITY;')
    op.drop_index('ix_extracted_attributes_tenant_attribute', table_name='extracted_attributes', schema='metadata')
    op.drop_table('extracted_attributes', schema='metadata')

    op.execute('DROP POLICY IF EXISTS extraction_jobs_tenant_policy ON metadata.extraction_jobs;')
    op.execute('ALTER TABLE metadata.extraction_jobs DISABLE ROW LEVEL SECURITY;')
    op.drop_index('ix_extraction_jobs_tenant_created', table_name='extraction_jobs', schema='metadata')
    op.drop_table('extraction_jobs', schema='metadata')
