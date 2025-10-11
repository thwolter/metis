from fastapi import Header, HTTPException, status

from core import get_settings

INTERNAL_AUTH_HEADER = 'X-Internal-Auth'


def require_internal_auth(
    token: str | None = Header(default=None, alias=INTERNAL_AUTH_HEADER),
) -> None:
    """Ensures requests include the expected internal authentication token."""
    settings = get_settings()
    expected = settings.internal_auth_token.get_secret_value().strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Internal auth token not configured',
        )
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or missing internal authentication token',
        )
