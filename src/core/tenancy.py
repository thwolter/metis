from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse
from uuid import UUID


def dsn_with_tenant(dsn: str, tenant_id: UUID) -> str:
    """Return a copy of the DSN with the tenant_id set in the query params."""
    parsed = urlparse(dsn)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    # Merge any existing options with our setting
    opts = query.get('options')
    new_opt = f'-c app.tenant_id={tenant_id}'
    if opts:
        if new_opt not in opts:
            opts = f'{opts} {new_opt}'
    else:
        opts = new_opt
    query['options'] = opts
    new_query = urlencode(query, doseq=True, quote_via=quote)  # type: ignore[bad-argument-type]
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )
