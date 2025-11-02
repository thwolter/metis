from uuid import uuid4


async def test_put_metadata_creates_versions(auth_client):
    document_id = uuid4()
    payload = {
        'metadata': {
            'document_type': 'Annual Report',
            'company_name': 'ACME AG',
        }
    }

    response = await auth_client.put(f'/v1/documents/{document_id}/metadata', json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body['version'] == 1
    assert body['metadata']['company_name'] == 'ACME AG'

    updated_payload = {
        'metadata': {
            'document_type': 'Annual Report',
            'company_name': 'ACME Group',
            'reporting_year': 2024,
        }
    }

    response = await auth_client.put(f'/v1/documents/{document_id}/metadata', json=updated_payload)
    assert response.status_code == 200
    body = response.json()
    assert body['version'] == 2
    assert body['metadata']['company_name'] == 'ACME Group'
    assert body['metadata']['reporting_year'] == 2024


async def test_delete_document_endpoint_removes_metadata(auth_client):
    document_id = uuid4()
    payload = {
        'metadata': {
            'document_type': 'Annual Report',
            'company_name': 'ACME AG',
        }
    }

    response = await auth_client.put(f'/v1/documents/{document_id}/metadata', json=payload)
    assert response.status_code == 200

    response = await auth_client.delete(f'/v1/documents/{document_id}')
    assert response.status_code == 204

    response = await auth_client.get(f'/v1/documents/{document_id}/metadata')
    assert response.status_code == 404

    response = await auth_client.delete(f'/v1/documents/{document_id}')
    assert response.status_code == 404
