from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from utils.vstore import get_collection_uuid


def _mock_cursor(row):
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = None
    return cursor


def test_get_collection_uuid_returns_string():
    conn = MagicMock()
    cursor = _mock_cursor((UUID('66fe9540-a7ba-4ac8-8fdf-00a6cb5680c9'),))
    conn.cursor.return_value = cursor

    value = get_collection_uuid(conn, 'test-collection')

    assert value == '66fe9540-a7ba-4ac8-8fdf-00a6cb5680c9'


def test_get_collection_uuid_missing_collection():
    conn = MagicMock()
    cursor = _mock_cursor(None)
    conn.cursor.return_value = cursor

    with pytest.raises(ValueError, match='test-collection'):
        get_collection_uuid(conn, 'test-collection')


def test_get_collection_uuid_empty_value():
    conn = MagicMock()
    cursor = _mock_cursor(('   ',))
    conn.cursor.return_value = cursor

    with pytest.raises(ValueError, match='empty UUID'):
        get_collection_uuid(conn, 'test-collection')
