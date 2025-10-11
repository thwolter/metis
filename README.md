## Security

All metadata API routes now require the `X-Internal-Auth` header. Configure the expected value via the `INTERNAL_AUTH_TOKEN` environment variable (defaults to `dev-internal-token` for local development). Health probes remain unauthenticated.
