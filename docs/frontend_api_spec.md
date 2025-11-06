# Metadata API Specification (Frontend Contract)

## Base URL and Authentication
- **Service root**: all versioned endpoints live under `/v1`. Combine with the environment host, for example `https://metadata.internal.example.com/v1`.
- **Authentication**: every request must send `Authorization: Bearer <jwt>`. Tokens are decoded with [`tenauth`](https://thwolter.github.io/tenauth/) and must contain `tid` (tenant) and `sub` (user) claims. Missing or malformed tokens return `401 Unauthorized`.
- **Content type**: request and response bodies are JSON encoded using UTF-8.

## Common Data Structures

### ExtractionRequest (body)

| Field | Type | Notes |
| --- | --- | --- |
| `doc_id` | UUID | Identifier of the document whose attributes will be extracted. |
| `doc_type` | string | Document type key registered in the extraction attribute registry (e.g. `annual_report`). |
| `digest` | string (`SHA256B64`) | Digest used to filter chunks in the vector store. |
| `collection_name` | string | Vector store collection name. |
| `attributes` | string[] \| null | Optional subset of attribute names to extract (defaults to all registered attributes for the document type). |
| `model` | string \| null | Optional override for the extraction LLM model. |
| `retriever` | RetrievalConfig \| null | Optional overrides for max chunk counts, header boosts, and hint weights. |
| `dry_run` | boolean | When `true`, the pipeline emits streaming updates but skips persistence. |

### RetrievalConfig

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `max_chunks` | integer | `12` | Maximum chunks to retrieve per attribute. |
| `top_m` | integer | `3` | Upper bound on chunks passed to the map step. |
| `header_boost` | float | `0.5` | Multiplier applied when header hints match. |
| `semantic_weight` | float | `1.0` | Weight of semantic similarity. |
| `bm25_weight` | float | `0.5` | Weight of lexical / BM25 similarity. |
| `hints_weight` | float | `0.3` | Bonus applied when attribute hints match the chunk text. |

### AttributeResult

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string | Attribute identifier. |
| `value` | any \| null | Normalised attribute value. |
| `confidence` | float \| null | Confidence score in \[0, 1]. |
| `provenance` | string[] | Chunk IDs contributing to the decision. |
| `rationale` | string \| null | Optional free-form rationale. |
| `validation_issues` | object[] | Any validation warnings recorded during the pipeline. |
| `status` | `"accepted"` \| `"abstained"` \| `"error"` | Final disposition. |

### MetadataSchema

Manual metadata endpoints continue to use the existing `MetadataSchema`. Fields mirror the historic metadata payload (document type, company fields, tags, etc.).

### ExtractionJobStatus (enum)
`queued`, `running`, `completed`, `failed`, `canceled`.

### Standard Error Payload
Most backend validation and lookup errors follow FastAPI’s default shape:

```json
{"detail": "Job not found"}
```

Validation errors (`422`) return an array of issues under `detail`.

## Endpoint Overview

| Method | Path | Summary |
| --- | --- | --- |
| POST | `/v1/extraction/run` | Launch an attribute extraction job. |
| GET | `/v1/extraction/jobs/{job_id}` | Retrieve extraction job status (and persisted results when ready). |
| POST | `/v1/extraction/jobs/{job_id}/cancel` | Request extraction job cancellation. |
| WS | `/v1/jobs/{job_id}/stream` | Subscribe to live extraction job status updates. |
| GET | `/v1/documents/{document_id}/metadata` | Fetch versioned metadata for a document. |
| PUT | `/v1/documents/{document_id}/metadata` | Manually upsert metadata (bypasses the extraction pipeline). |
| DELETE | `/v1/documents/{document_id}` | Remove a document together with its metadata versions and extraction jobs. |
| GET | `/v1/documents/search` | Search documents by metadata attributes. |
| GET | `/healthz`, `/readyz` | Liveness and readiness probes (unauthenticated). |

## Extraction

### POST `/v1/extraction/run`
Launch an attribute-centric extraction job. Jobs are idempotent per `(tenant_id, doc_id, doc_type)`; resubmitting the same triplet while the job is queued overwrites model and retriever settings.

**Success response**
- `202 Accepted` with `ExtractionJobResponse`:

```json
{
  "job_id": "4f3c6857-0405-454a-9695-b868aee81af7",
  "doc_id": "be9f6304-5ea1-4690-843b-7192617b61d4",
  "doc_type": "annual_report",
  "attributes": {},
  "model": "openai:gpt-4o-mini",
  "model_version": "2025-10-15",
  "started_at": "2025-11-06T16:00:00Z",
  "completed_at": null,
  "errors": [],
  "status_url": "https://metadata.internal.example.com/v1/extraction/jobs/4f3c6857-0405-454a-9695-b868aee81af7",
  "stream_url": "https://metadata.internal.example.com/v1/jobs/4f3c6857-0405-454a-9695-b868aee81af7/stream"
}
```

**Error responses**
- `401 Unauthorized`
- `422 Unprocessable Entity` for malformed UUIDs or missing `digest` / `collection_name`.

### GET `/v1/extraction/jobs/{job_id}`
Return job status, sequence counter, and persisted results when the job finishes.

**Success response**
- `200 OK` with `ExtractionJobStatusResponse`:

```json
{
  "job_id": "4f3c6857-0405-454a-9695-b868aee81af7",
  "doc_id": "be9f6304-5ea1-4690-843b-7192617b61d4",
  "doc_type": "annual_report",
  "status": "completed",
  "created_at": "2025-11-06T16:00:00Z",
  "started_at": "2025-11-06T16:00:01Z",
  "finished_at": "2025-11-06T16:00:18Z",
  "error": null,
  "seq": 37,
  "results": {
    "company_name": {
      "value": "SEFE Storage GmbH",
      "confidence": 0.91,
      "provenance": ["c-017"],
      "rationale": "Company name identified in shareholder section"
    }
  }
}
```

`results` is omitted until the job reaches the `completed` state.

**Error responses**
- `401 Unauthorized`
- `404 Not Found` when the job ID is unknown or belongs to another tenant.

### POST `/v1/extraction/jobs/{job_id}/cancel`
Request cancellation of a queued or running extraction job. Terminal jobs return their existing status.

**Success response**
- `202 Accepted` with `ExtractionJobCancelResponse`:

```json
{"job_id": "4f3c6857-0405-454a-9695-b868aee81af7", "status": "canceled"}
```

**Error responses**
- `401 Unauthorized`
- `404 Not Found`

### WS `/v1/jobs/{job_id}/stream`
Subscribe to real-time extraction status updates. Messages implement `ExtractionStatusPayload` and increase the `seq` counter monotonically.

**Authentication**
- Preferred: send `Authorization: Bearer <jwt>` during the WebSocket handshake.
- Alternative: provide `?access_token=<jwt>` (or `?token=`) on the query string.
- For clients requiring subprotocols, include `Sec-WebSocket-Protocol: access_token=<jwt>`.

Requests without a valid token are closed with code `1008` and a descriptive reason.

**Message flow**
- The server accepts the connection only if the job exists; otherwise it returns a `1008` `Job not found` close.
- On connect, the first payload mirrors `GET /v1/extraction/jobs/{job_id}` if the job already finished, or emits the latest event otherwise.
- Subsequent payloads stream events (`job.started`, `chunk.mapped`, `attribute.*`, `job.partial`) until a terminal `job.completed`, `job.failed`, or `job.canceled` event is sent.
- After the job reaches a terminal state the server closes the socket with code `1000` (normal closure).

**Example terminal payload**

```json
{
  "seq": 37,
  "timestamp": "2025-11-06T16:00:18Z",
  "job_id": "4f3c6857-0405-454a-9695-b868aee81af7",
  "doc_id": "be9f6304-5ea1-4690-843b-7192617b61d4",
  "doc_type": "annual_report",
  "event": "job.completed",
  "status": "completed",
  "progress": null,
  "attribute": null,
  "provenance": null,
  "summary": null,
  "errors": null,
  "attributes": null,
  "results": {
    "company_name": {"value": "SEFE Storage GmbH", "confidence": 0.91, "provenance": ["c-017"]}
  }
}
```

## Manual Metadata

### GET `/v1/documents/{document_id}/metadata`
Fetch a specific metadata version. `version` can be `latest` or `v{number}` (e.g. `v3`). The response wraps the stored `MetadataSchema` plus fingerprint and extraction timestamp.

### PUT `/v1/documents/{document_id}/metadata`
Persist a manual metadata payload. If the payload differs from the latest version, the service records a new `MetadataSchema` version.

**Success response**
- `200 OK` with `MetadataVersionResponse` (document ID, new version number, fingerprint, extraction timestamp, payload).

**Error responses**
- `401 Unauthorized`
- `422 Unprocessable Entity` for validation issues.

### DELETE `/v1/documents/{document_id}`
Delete a document, its metadata versions, and any extraction jobs. Cascades through the metadata schema.

**Success response**
- `204 No Content`

**Error responses**
- `401 Unauthorized`
- `404 Not Found`

## Search

### GET `/v1/documents/search`
Search documents by metadata payload. Query strings combine case-insensitive filters joined by `&`. Use `field:value` to constrain a specific metadata field.

**Example**
- `q=acme&tag:finance`

**Success response**
- `200 OK` with `DocumentSearchResponse` (`document_ids` + `digests` arrays of equal length).

**Error responses**
- `401 Unauthorized`
- `400 Bad Request` for malformed filters.

## Health Checks

### GET `/healthz`
Always returns `{"status": "ok"}`. Intended for liveness probes.

### GET `/readyz`
Returns `{"status": "ready"}` once the application has completed startup (DB connectivity, configuration, etc.).
