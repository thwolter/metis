"""Add gen_random_uuid() default for documents.document_id."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '0008_document_id_defaults'
down_revision = '0007_tenant_id_defaults'
branch_labels = None
depends_on = None

DOCUMENT_ID_DEFAULT = sa.text('gen_random_uuid()')


def upgrade() -> None:
    op.alter_column(
        'documents',
        'document_id',
        schema='metadata',
        existing_type=postgresql.UUID(as_uuid=True),
        server_default=DOCUMENT_ID_DEFAULT,
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'documents',
        'document_id',
        schema='metadata',
        existing_type=postgresql.UUID(as_uuid=True),
        server_default=None,
        existing_nullable=False,
    )
