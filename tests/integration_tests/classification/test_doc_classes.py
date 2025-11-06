from __future__ import annotations

import pytest

from classification.models import DocClass


@pytest.mark.asyncio
async def test_list_doc_classes_returns_enabled_only(auth_client, auth_session):
    auth_session.add_all(
        [
            DocClass(class_name='invoice', enabled=True),
            DocClass(class_name='receipt', enabled=True),
            DocClass(class_name='draft', enabled=False),
        ]
    )
    await auth_session.commit()

    response = await auth_client.get('/api/classification/doc-classes')

    assert response.status_code == 200
    assert response.json() == ['invoice', 'receipt']
