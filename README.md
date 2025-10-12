## Security

All metadata API routes now require an `Authorization: Bearer <jwt>` header. Tokens are parsed with `tenauth` and must include a `tid` (tenant) and `sub` (user) claim. Health probes remain unauthenticated.

## Manual Metadata Updates

Use `PUT /v1/documents/{document_id}/metadata` with a body shaped as `{"metadata": {...}}` to persist a new metadata version without queueing the agent. Each call records a new version only when the payload changes.
