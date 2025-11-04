"""classification_models

Revision ID: 51f60d80d587
Revises: 0003_add_audit_columns
Create Date: 2025-11-03 18:14:02.225169

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '0004_classification_models'
down_revision = '0003_add_audit_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add classification tables only. Do not alter or drop unrelated objects."""
    # doc_classes
    op.create_table(
        'doc_classes',
        sa.Column('class', sa.String(length=100), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False
        ),
        sa.PrimaryKeyConstraint('class'),
        schema='classification',
    )

    # class_prototypes
    op.create_table(
        'class_prototypes',
        sa.Column('class', sa.String(length=100), nullable=False),
        sa.Column('centroid', sa.JSON(), nullable=False),
        sa.Column('dispersion', sa.Float(), nullable=False),
        sa.Column('n_docs', sa.Integer(), nullable=False),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ['class'], ['classification.doc_classes.class'], name='fk_prototypes_class', ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('class'),
        schema='classification',
    )

    # classification_runs
    op.create_table(
        'classification_runs',
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('document_id', sa.Uuid(), nullable=False),
        sa.Column('predicted_class', sa.String(length=100), nullable=True),
        sa.Column('prob', sa.Float(), nullable=False),
        sa.Column('margin', sa.Float(), nullable=False),
        sa.Column('chunks_used', sa.Integer(), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ['predicted_class'], ['classification.doc_classes.class'], name='fk_classruns_class', ondelete='SET NULL'
        ),
        sa.ForeignKeyConstraint(
            ['tenant_id', 'document_id'],
            ['metadata.documents.tenant_id', 'metadata.documents.document_id'],
            name='fk_classruns_document',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('run_id'),
        schema='classification',
    )
    op.create_index(
        'ix_classruns_doc_created',
        'classification_runs',
        ['tenant_id', 'document_id', 'created_at'],
        unique=False,
        schema='classification',
    )

    # header_weights
    op.create_table(
        'header_weights',
        sa.Column('class', sa.String(length=100), nullable=False),
        sa.Column('pattern', sa.Text(), nullable=False),
        sa.Column('is_regex', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ['class'], ['classification.doc_classes.class'], name='fk_header_weights_class', ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('class', 'pattern'),
        schema='classification',
    )


def downgrade() -> None:
    """Drop classification tables only, reverse of upgrade."""
    op.drop_table('header_weights', schema='classification')
    op.drop_index('ix_classruns_doc_created', table_name='classification_runs', schema='classification')
    op.drop_table('classification_runs', schema='classification')
    op.drop_table('class_prototypes', schema='classification')
    op.drop_table('doc_classes', schema='classification')
