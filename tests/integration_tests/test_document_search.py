from uuid import uuid4


async def _upsert_metadata(api_client, document_id, metadata):
    response = await api_client.put(f'/v1/documents/{document_id}/metadata', json={'metadata': metadata})
    assert response.status_code == 200, response.text


async def test_simple_query_matches_any_field(auth_client):
    doc_a = uuid4()
    doc_b = uuid4()

    await _upsert_metadata(
        auth_client,
        doc_a,
        {
            'company_name': 'ACME Holdings',
            'document_type': 'Annual Report',
            'tags': ['finance'],
        },
    )
    await _upsert_metadata(
        auth_client,
        doc_b,
        {
            'company_name': 'Globex',
            'document_type': 'Quarterly Statement',
        },
    )

    response = await auth_client.get('/v1/documents/search', params={'q': 'acme'})
    assert response.status_code == 200
    body = response.json()
    assert body['document_ids'] == [str(doc_a)]
    assert body['digests'] == [None]


async def test_filter_query_matches_specific_field(auth_client):
    doc_a = uuid4()
    doc_b = uuid4()

    await _upsert_metadata(
        auth_client,
        doc_a,
        {
            'company_name': 'ACME Holdings',
            'tags': ['Energy', 'Outlook'],
        },
    )
    await _upsert_metadata(
        auth_client,
        doc_b,
        {
            'company_name': 'Globex',
            'tags': ['Finance'],
        },
    )

    response = await auth_client.get('/v1/documents/search', params={'q': 'tag:energy'})
    assert response.status_code == 200
    body = response.json()
    assert body['document_ids'] == [str(doc_a)]
    assert body['digests'] == [None]


async def test_combined_filters_apply_and_logic(auth_client):
    doc_a = uuid4()
    doc_b = uuid4()

    await _upsert_metadata(
        auth_client,
        doc_a,
        {
            'company_name': 'Acme Inc',
            'tags': ['Finance'],
        },
    )
    await _upsert_metadata(
        auth_client,
        doc_b,
        {
            'company_name': 'Acme Logistics',
            'tags': ['Operations'],
        },
    )

    response = await auth_client.get('/v1/documents/search', params={'q': 'Acme Inc & tag:finance'})
    assert response.status_code == 200
    body = response.json()
    assert body['document_ids'] == [str(doc_a)]
    assert body['digests'] == [None]


async def test_unknown_field_returns_bad_request(auth_client):
    doc_a = uuid4()

    await _upsert_metadata(
        auth_client,
        doc_a,
        {
            'company_name': 'ACME Holdings',
            'tags': ['finance'],
        },
    )

    response = await auth_client.get('/v1/documents/search', params={'q': 'unknown:energy'})
    assert response.status_code == 400
    assert response.json()['detail'].startswith('Unknown metadata field')
