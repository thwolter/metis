# Metadata API Specification (Frontend Contract)

## Base URL and Authentication
- **Service root**: all versioned endpoints live under `/v1`. Combine with the environment host, for example `https://metadata.internal.example.com/v1`.
- **Authentication**: every request must send `Authorization: Bearer <jwt>`. Tokens are decoded with `tenauth` and must contain `tid` (tenant) and `sub` (user) claims. Missing or malformed tokens return `401 Unauthorized`.
- **Content type**: request and response bodies are JSON encoded using UTF-8.

## Common Data Structures

### ContextSchema
| Field | Type | Notes |
| --- | --- | --- |
| `digest` | string (`SHA256B64`) | Base64-encoded SHA-256 hash of the document. Used for idempotency. |
| `collection_name` | string | Logical collection in the vector store. |
| `tenant_id` | UUID | Tenant identifier that scopes storage and permissions. |

### MetadataSchema
| Field | Type | Notes |
| --- | --- | --- |
| `document_type` | string \| null | e.g. `"Annual Report"`. |
| `company_name` | string \| null | Primary company name. |
| `parent_company` | string \| null | Immediate parent. |
| `ultimate_parent_company` | string \| null | Top-level parent. |
| `reporting_date` | date \| null | ISO-8601 date (`YYYY-MM-DD`). |
| `reporting_year` | integer \| null | e.g. `2023`. |
| `call_date` | date \| null | When the document was received. |
| `company_register` | string \| null | Register name. |
| `register_number` | string \| null | Registration identifier. |
| `tags` | string[] \| null | Arbitrary document tags. |

### JobStatus (enum)
`queued`, `running`, `succeeded`, `failed`, `canceled`.

### Standard Error Payload
Most backend validation and lookup errors follow FastAPI’s default shape:

```json
{"detail": "Job not found"}
```

Validation errors (`422`) return an array of issues under `detail`.

## Endpoint Overview
| Method | Path | Summary |
| --- | --- | --- |
| POST | `/v1/metadata` | Create (or reuse) a metadata extraction job. |
| POST | `/v1/documents/{document_id}/rebuild` | Rebuild metadata for an existing document. |
| GET | `/v1/jobs/{job_id}` | Retrieve job status (and result link when ready). |
| DELETE | `/v1/jobs/{job_id}` | Request job cancellation. |
| GET | `/v1/documents/{document_id}/metadata` | Fetch versioned metadata for a document. |
| PUT | `/v1/documents/{document_id}/metadata` | Manually upsert metadata (bypasses agent). |
| GET | `/healthz`, `/readyz` | Liveness and readiness probes (unauthenticated). |

## Endpoint Details

### POST `/v1/metadata`
Create a metadata extraction job. Jobs are idempotent per `(tenant_id, document_id, profile, ingestion_fingerprint)`.

**Query string**
| Name | Type | Default | Notes |
| --- | --- | --- | --- |
| `wait_for_secs` | integer | `0` | Optional polling window (0–30). The API blocks up to this many seconds, returning `result_url` immediately if the job succeeds within the window. |

**Request body**
| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `document_id` | UUID \| null | optional | If omitted, the backend derives an ID from `context.digest`. |
| `context` | ContextSchema | yes | See schema above. |
| `metadata` | MetadataSchema \| null | optional | Seed values. Agent output may overwrite unlocked fields. |
| `locked_fields` | string[] \| null | optional | Fields that must remain unchanged even if the agent proposes values. Empty list or omission allows full overwrite. |
| `profile` | string | yes (default `"default"`) | Selects the agent strategy. |
| `priority` | integer (0–10) \| null | optional (default `5`) | Lower numbers process sooner. |
| `callback_url` | URL \| null | optional | Invoked after success. |
| `idempotency_key` | string (≤128) \| null | optional | Overrides default fingerprint (`context.digest`). Enables client-managed idempotency. |

**Success response**
- `202 Accepted` with `JobCreatedResponse`:

```json
{
  "job_id": "4f3c6857-0405-454a-9695-b868aee81af7",
  "document_id": "be9f6304-5ea1-4690-843b-7192617b61d4",
  "status_url": "https://metadata.internal.example.com/v1/jobs/4f3c6857-0405-454a-9695-b868aee81af7",
  "result_url": "https://metadata.internal.example.com/v1/documents/be9f6304-5ea1-4690-843b-7192617b61d4/metadata?version=latest"
}
```

Note: `result_url` is present only if the job finishes successfully during the wait window.

**Error responses**
- `401 Unauthorized` when the Bearer token is missing or invalid.
- `422 Unprocessable Entity` for validation errors (e.g., malformed UUIDs or dates).

### POST `/v1/documents/{document_id}/rebuild`
Kick off a rebuild job for an existing document. Body accepts the same payload as `CreateJobDTO`; the `document_id` path parameter overrides any value supplied in the body.

**Success response**
- `202 Accepted` with `JobCreatedResponse` (same shape as above, `result_url` omitted until completion).

**Error responses**
- `401 Unauthorized`
- `422 Unprocessable Entity`

### GET `/v1/jobs/{job_id}`
Return job status and progress metadata.

**Success response**
- `200 OK` with `JobStatusResponse`:

```json
{
  "job_id": "4f3c6857-0405-454a-9695-b868aee81af7",
  "document_id": "be9f6304-5ea1-4690-843b-7192617b61d4",
  "tenant_id": "b46a635d-aead-4bc9-9051-01ede4cbb2de",
  "status": "running",
  "retries": 0,
  "priority": 5,
  "created_at": "2024-01-16T09:53:10.517Z",
  "started_at": "2024-01-16T09:53:11.012Z",
  "finished_at": null,
  "error_type": null,
  "error_msg": null,
  "result_url": null
}
```

- When `status` is `succeeded`, `result_url` points to the latest metadata version.

**Error responses**
- `401 Unauthorized`
- `404 Not Found` when the job ID is unknown.

### DELETE `/v1/jobs/{job_id}`
Request cancellation of an in-flight job. Completed jobs return their existing status without changes.

**Success response**
- `202 Accepted` with `JobCancelResponse`:

```json
{"job_id": "4f3c6857-0405-454a-9695-b868aee81af7", "status": "canceled"}
```

**Error responses**
- `401 Unauthorized`
- `404 Not Found`

### GET `/v1/documents/{document_id}/metadata`
Fetch a specific or latest metadata version.

**Query string**
| Name | Type | Default | Notes |
| --- | --- | --- | --- |
| `version` | string \| null | `"latest"` | Supports `"latest"` or explicit versions like `"v3"` / `"3"`. |

**Success response**
- `200 OK` with `MetadataVersionResponse`:

```json
{
  "document_id": "be9f6304-5ea1-4690-843b-7192617b61d4",
  "version": 3,
  "fingerprint": "b407f6955d4f5ef1f6798cbae6e17c1ea401f83d4580598d77077d4a2ee2167a",
  "extracted_on": "2024-01-16T09:55:03.144Z",
  "metadata": {
    "document_type": "Annual Report",
    "company_name": "Acme Corp",
    "parent_company": null,
    "ultimate_parent_company": null,
    "reporting_date": "2023-12-31",
    "reporting_year": 2023,
    "call_date": null,
    "company_register": "Delaware",
    "register_number": "1234567",
    "tags": ["finance", "annual"]
  }
}
```

**Error responses**
- `401 Unauthorized`
- `404 Not Found` when no matching document/version exists.
- `422 Unprocessable Entity` when `version` does not match the regex `latest` or `v<number>`.

### PUT `/v1/documents/{document_id}/metadata`
Persist a manual metadata version without running the extraction agent. The backend increments the version counter unless the incoming payload matches the latest fingerprint exactly.

**Request body**

```json
{
  "metadata": {
    "...": "See MetadataSchema above"
  }
}
```

**Success response**
- `200 OK` with `MetadataVersionResponse` (same shape as the GET response).

**Error responses**
- `401 Unauthorized`
- `422 Unprocessable Entity`

## Health Probes
- `GET /healthz` → `{"status": "ok"}`
- `GET /readyz` → `{"status": "ready"}`

These endpoints are unauthenticated and intended for platform monitoring.

## Additional Notes for Frontend Integration
- Prefer using the URLs returned by `status_url` and `result_url` rather than reconstructing paths manually; they already include the correct host and versioning.
- Jobs are processed asynchronously. Poll `/v1/jobs/{job_id}` until `status` transitions to a terminal state (`succeeded`, `failed`, or `canceled`). A `result_url` is only meaningful once the job succeeds.
- When supplying `metadata.locked_fields`, ensure the array contains metadata keys exactly as defined in `MetadataSchema`.
- The backend emits callbacks (POST requests) to `callback_url` only on success; the callback payload mirrors `MetadataVersionResponse`.
