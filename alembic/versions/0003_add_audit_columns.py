"""Introduce audit columns for metadata tables."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '0003_add_audit_columns'
down_revision = '0002_document_relationships'
branch_labels = None
depends_on = None

UUID_ZERO = '00000000-0000-0000-0000-000000000000'


def upgrade() -> None:
    op.add_column(
        'metadata_jobs',
        sa.Column(
            'updated_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=True,
        ),
        schema='metadata',
    )
    op.add_column(
        'metadata_jobs',
        sa.Column(
            'created_by',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("current_setting('app.user_id', true)::uuid"),
            nullable=True,
        ),
        schema='metadata',
    )
    op.add_column(
        'metadata_jobs',
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        schema='metadata',
    )

    op.add_column(
        'documents',
        sa.Column(
            'updated_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=True,
        ),
        schema='metadata',
    )
    op.add_column(
        'documents',
        sa.Column(
            'created_by',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("current_setting('app.user_id', true)::uuid"),
            nullable=True,
        ),
        schema='metadata',
    )
    op.add_column(
        'documents',
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        schema='metadata',
    )

    op.add_column(
        'document_metadata',
        sa.Column(
            'created_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=True,
        ),
        schema='metadata',
    )
    op.add_column(
        'document_metadata',
        sa.Column(
            'updated_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=True,
        ),
        schema='metadata',
    )
    op.add_column(
        'document_metadata',
        sa.Column(
            'created_by',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("current_setting('app.user_id', true)::uuid"),
            nullable=True,
        ),
        schema='metadata',
    )
    op.add_column(
        'document_metadata',
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        schema='metadata',
    )

    op.execute(
        """
        UPDATE metadata.metadata_jobs
        SET updated_at = COALESCE(updated_at, created_at)
        """
    )
    op.execute(
        """
        UPDATE metadata.metadata_jobs
        SET created_by = user_id
        WHERE created_by IS NULL
        """
    )

    op.execute(
        """
        WITH first_jobs AS (
            SELECT tenant_id, document_id, user_id
            FROM (
                SELECT
                    tenant_id,
                    document_id,
                    user_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY tenant_id, document_id
                        ORDER BY created_at NULLS LAST, job_id
                    ) AS rn
                FROM metadata.metadata_jobs
                WHERE user_id IS NOT NULL
            ) ranked_jobs
            WHERE rn = 1
        )
        UPDATE metadata.documents AS d
        SET created_by = fj.user_id
        FROM first_jobs AS fj
        WHERE d.created_by IS NULL
          AND d.tenant_id = fj.tenant_id
          AND d.document_id = fj.document_id
        """
    )
    op.execute(
        sa.text(
            """
            UPDATE metadata.documents
            SET created_by = :uuid_zero
            WHERE created_by IS NULL
            """
        ).bindparams(uuid_zero=UUID_ZERO)
    )
    op.execute(
        """
        UPDATE metadata.documents
        SET updated_at = COALESCE(updated_at, created_at)
        """
    )

    op.execute(
        """
        UPDATE metadata.document_metadata
        SET created_at = COALESCE(created_at, extracted_on),
            updated_at = COALESCE(updated_at, extracted_on)
        """
    )
    op.execute(
        sa.text(
            """
            UPDATE metadata.document_metadata
            SET created_by = :uuid_zero
            WHERE created_by IS NULL
            """
        ).bindparams(uuid_zero=UUID_ZERO)
    )

    op.alter_column(
        'metadata_jobs',
        'updated_at',
        schema='metadata',
        nullable=False,
        existing_type=sa.TIMESTAMP(timezone=True),
    )
    op.alter_column(
        'metadata_jobs',
        'created_by',
        schema='metadata',
        nullable=False,
        existing_type=postgresql.UUID(as_uuid=True),
    )

    op.alter_column(
        'documents',
        'updated_at',
        schema='metadata',
        nullable=False,
        existing_type=sa.TIMESTAMP(timezone=True),
    )
    op.alter_column(
        'documents',
        'created_by',
        schema='metadata',
        nullable=False,
        existing_type=postgresql.UUID(as_uuid=True),
    )

    op.alter_column(
        'document_metadata',
        'created_at',
        schema='metadata',
        nullable=False,
        existing_type=sa.TIMESTAMP(timezone=True),
    )
    op.alter_column(
        'document_metadata',
        'updated_at',
        schema='metadata',
        nullable=False,
        existing_type=sa.TIMESTAMP(timezone=True),
    )
    op.alter_column(
        'document_metadata',
        'created_by',
        schema='metadata',
        nullable=False,
        existing_type=postgresql.UUID(as_uuid=True),
    )


def downgrade() -> None:
    op.drop_column('document_metadata', 'updated_by', schema='metadata')
    op.drop_column('document_metadata', 'created_by', schema='metadata')
    op.drop_column('document_metadata', 'updated_at', schema='metadata')
    op.drop_column('document_metadata', 'created_at', schema='metadata')

    op.drop_column('documents', 'updated_by', schema='metadata')
    op.drop_column('documents', 'created_by', schema='metadata')
    op.drop_column('documents', 'updated_at', schema='metadata')

    op.drop_column('metadata_jobs', 'updated_by', schema='metadata')
    op.drop_column('metadata_jobs', 'created_by', schema='metadata')
    op.drop_column('metadata_jobs', 'updated_at', schema='metadata')
