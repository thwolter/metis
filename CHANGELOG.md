## 0.4.1 (2025-11-02)

### Refactor

- **tests + metadata**: replace custom token/auth context utils with shared functions

## 0.4.0 (2025-11-02)

### Feat

- **tests + metadata**: improve job status streaming and WebSocket testing
- **metadata**: include digests in document search results
- **metadata + documents**: add audit fields, cascading relations, and document search - Added audit fields (created_at, updated_at, created_by, updated_by) to metadata tables with migration scripts and model updates. - Introduced documents table with cascading relationships, RLS, and DELETE endpoint for full cleanup. - Streamlined queueing architecture, added /v1/documents/search for metadata-based lookup, and improved observability with DramatiqMonitoringMiddleware. - Migrated tests to async PostgreSQL/Redis containers, updated API docs, and removed legacy _access helper in favour of session-based AccessContext.
- introduce dynamic CORS origins configuration and improve utils
- enhance metadata handling and async operations

## 0.3.0 (2025-10-25)

### Feat

- restructure infrastructure and bootstrap database roles
- add role validation and creation for metadata_rw
- add CORS middleware to support frontend development

## 0.2.1 (2025-10-13)

### Refactor

- rename project from `classifier` to `metis` in `pyproject.toml`

## 0.2.0 (2025-10-12)

### Feat

- replace `tenant_id` in job context with implicit tenant injection
- add tenant isolation with RLS and enhance access context handling

### Refactor

- replace internal auth with tenant-based authorization

## 0.1.0 (2025-10-11)

### Feat

- add support for manual metadata updates with versioning
- enforce internal authentication for metadata API routes
- add OpenTelemetry-based observability integration
- add Redis-backed task queue integration and refactor FastAPI app structure
- implement comprehensive metadata service with FastAPI, task orchestration, and database integration
- enhance metadata extraction and tagging, add prompt utilities, and update dependencies

### Refactor

- streamline task processing and Docker setup, enhance metadata workflows

## 0.0.2 (2025-10-10)

### Fix

- cleanup and install loguru
