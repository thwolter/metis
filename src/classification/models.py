from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, relationship
from sqlmodel import Field, Relationship

from metadata.models import BaseSQLModel, Document
from utils.fields import created_at_field, updated_at_field


class DocClass(BaseSQLModel, table=True):
    """Supported document classes."""

    __tablename__ = 'doc_classes'  # type: ignore[bad-argument-type]
    __table_args__ = ({'schema': 'classification'},)

    # 'class' is awkward in Python. Use attribute class_name mapped to column 'class'.
    class_name: str = Field(sa_column=Column('class', String(100), primary_key=True))
    enabled: bool = Field(sa_column=Column(Boolean, nullable=False, server_default='true'))
    created_at: datetime = created_at_field()

    # Relationships
    prototypes: Mapped[list['ClassPrototype']] = Relationship(
        sa_relationship=relationship(
            'ClassPrototype',
            back_populates='doc_class',
            cascade='all, delete-orphan',
        )
    )
    header_weights: Mapped[list['HeaderWeight']] = Relationship(
        sa_relationship=relationship(
            'HeaderWeight',
            back_populates='doc_class',
            cascade='all, delete-orphan',
        )
    )


class ClassPrototype(BaseSQLModel, table=True):
    """Per-class centroid and stats.
    Note: centroid stored as JSON[List[float]] to avoid pgvector dependency in this module.
    """

    __tablename__ = 'class_prototypes'  # type: ignore[bad-argument-type]
    __table_args__ = (
        ForeignKeyConstraint(
            ['class'],
            ['classification.doc_classes.class'],
            name='fk_prototypes_class',
            ondelete='CASCADE',
        ),
        {'schema': 'classification'},
    )

    class_name: str = Field(sa_column=Column('class', String(100), primary_key=True))
    # Centroid as JSON to keep this module self-contained. Your batch job can read/write pgvector elsewhere if preferred.
    centroid: list[float] = Field(sa_column=Column(JSON, nullable=False))
    dispersion: float = Field(sa_column=Column(Float, nullable=False))
    n_docs: int
    updated_at: datetime = updated_at_field()

    # Relationship backref
    doc_class: Mapped['DocClass'] = Relationship(sa_relationship=relationship('DocClass', back_populates='prototypes'))


class HeaderWeight(BaseSQLModel, table=True):
    """Header lexicon for class evidence priors."""

    __tablename__ = 'header_weights'  # type: ignore[bad-argument-type]
    __table_args__ = (
        ForeignKeyConstraint(
            ['class'],
            ['classification.doc_classes.class'],
            name='fk_header_weights_class',
            ondelete='CASCADE',
        ),
        {'schema': 'classification'},
    )

    class_name: str = Field(sa_column=Column('class', String(100), primary_key=True))
    pattern: str = Field(sa_column=Column(Text, primary_key=True))
    is_regex: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    weight: float = Field(sa_column=Column(Float, nullable=False))

    doc_class: Mapped['DocClass'] = Relationship(
        sa_relationship=relationship('DocClass', back_populates='header_weights')
    )


class ClassificationRun(BaseSQLModel, table=True):
    """Classification decisions per document for audit and calibration."""

    __tablename__ = 'classification_runs'  # type: ignore[bad-argument-type]
    __table_args__ = (
        # composite FK to documents for cascade on document deletion
        ForeignKeyConstraint(
            ['tenant_id', 'document_id'],
            ['metadata.documents.tenant_id', 'metadata.documents.document_id'],
            name='fk_classruns_document',
            ondelete='CASCADE',
        ),
        # FK to class for cascade on class deletion
        ForeignKeyConstraint(
            ['predicted_class'],
            ['classification.doc_classes.class'],
            name='fk_classruns_class',
            ondelete='SET NULL',  # keep the run but null out class if class removed
        ),
        Index('ix_classruns_doc_created', 'tenant_id', 'document_id', 'created_at'),
        {'schema': 'classification'},
    )

    run_id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: UUID
    document_id: UUID
    predicted_class: str | None = Field(default=None, sa_column=Column('predicted_class', String(100), nullable=True))
    prob: float = Field(sa_column=Column(Float, nullable=False))
    margin: float = Field(sa_column=Column(Float, nullable=False))
    chunks_used: int
    config: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = created_at_field()

    # Relationships
    document: Mapped['Document'] = Relationship(sa_relationship=relationship('Document'))
