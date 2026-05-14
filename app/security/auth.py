"""FastAPI auth dependencies — JWT bearer + API key."""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.security.jwt import decode_token

_settings = get_settings()
_bearer = HTTPBearer(auto_error=False)


def _get_current_subject(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> str:
    """Extract and validate the JWT bearer token. Returns subject string."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return payload["sub"]


def require_auth(subject: Annotated[str, Depends(_get_current_subject)]) -> str:
    """FastAPI dependency: require a valid JWT or API key."""
    return subject


def require_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> str:
    """Accept either a JWT OR the static ACTIONS_API_KEY for GitHub Actions."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth required")

    token = credentials.credentials

    # Check static API key first (for GitHub Actions service account)
    if secrets.compare_digest(token, _settings.actions_api_key):
        return "github-actions"

    # Fall back to JWT
    try:
        payload = decode_token(token)
        return payload["sub"]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
