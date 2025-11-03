from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field

from core.config import get_settings

APP_SCHEMA = get_settings().db_schema


def created_at_field() -> Any:
    """UTC created_at timestamp with default now()."""
    return Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("timezone('utc', now())"),
            default=lambda: datetime.now(timezone.utc),
        )
    )


def updated_at_field() -> Any:
    """UTC updated_at timestamp with server default now()."""
    return Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=text("timezone('utc', now())"),
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc),
        )
    )


def created_by_field() -> Any:
    """Created by user UUID sourced from PostgreSQL setting app.user_id."""
    return Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            nullable=False,
            server_default=text("current_setting('app.user_id', true)::uuid"),
        )
    )


def updated_by_field() -> Any:
    """Updated by user UUID sourced from PostgreSQL setting app.user_id."""
    return Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            nullable=True,
            onupdate=text("current_setting('app.user_id', true)::uuid"),
        )
    )
