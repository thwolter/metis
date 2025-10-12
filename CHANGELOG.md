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
