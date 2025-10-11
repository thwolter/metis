## Security

All metadata API routes now require the `X-Internal-Auth` header. Configure the expected value via the `INTERNAL_AUTH_TOKEN` environment variable (defaults to `dev-internal-token` for local development). Health probes remain unauthenticated.

## Manual Metadata Updates

Use `PUT /v1/documents/{document_id}/metadata` with a body shaped as `{"metadata": {...}}` to persist a new metadata version without queueing the agent. Each call records a new version only when the payload changes.
