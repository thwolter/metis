"""Add server defaults for tenant_id columns to match tenant_id_field."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '0007_tenant_id_defaults'
down_revision = '0006_extraction_tables'
branch_labels = None
depends_on = None

TENANT_DEFAULT = sa.text("current_setting('app.tenant_id', true)::uuid")


def upgrade() -> None:
    op.alter_column(
        'documents',
        'tenant_id',
        schema='metadata',
        existing_type=postgresql.UUID(as_uuid=True),
        server_default=TENANT_DEFAULT,
        existing_nullable=False,
    )
    op.alter_column(
        'document_metadata',
        'tenant_id',
        schema='metadata',
        existing_type=postgresql.UUID(as_uuid=True),
        server_default=TENANT_DEFAULT,
        existing_nullable=False,
    )
    op.alter_column(
        'extraction_jobs',
        'tenant_id',
        schema='metadata',
        existing_type=postgresql.UUID(as_uuid=True),
        server_default=TENANT_DEFAULT,
        existing_nullable=False,
    )
    op.alter_column(
        'extracted_attributes',
        'tenant_id',
        schema='metadata',
        existing_type=postgresql.UUID(as_uuid=True),
        server_default=TENANT_DEFAULT,
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'extracted_attributes',
        'tenant_id',
        schema='metadata',
        existing_type=postgresql.UUID(as_uuid=True),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        'extraction_jobs',
        'tenant_id',
        schema='metadata',
        existing_type=postgresql.UUID(as_uuid=True),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        'document_metadata',
        'tenant_id',
        schema='metadata',
        existing_type=postgresql.UUID(as_uuid=True),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        'documents',
        'tenant_id',
        schema='metadata',
        existing_type=postgresql.UUID(as_uuid=True),
        server_default=None,
        existing_nullable=False,
    )
