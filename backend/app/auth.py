"""Local bearer-token auth.

One token, one user. Generated on first run, stored in .env, read by the
extension during setup. No accounts, no refresh tokens, no multi-tenant
concerns (§9 of the blueprint).
"""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from .config import get_settings


async def require_token(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: reject the request if the bearer token doesn't match."""
    expected = get_settings().ensure_auth_token()
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing Authorization header",
        )
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not secrets_compare(parts[1], expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
        )
    return parts[1]


def secrets_compare(a: str, b: str) -> bool:
    """Constant-time string compare to avoid timing side-channels."""
    if len(a) != len(b):
        return False
    out = 0
    for x, y in zip(a, b):
        out |= ord(x) ^ ord(y)
    return out == 0
