"""
Internal authentication: the Go backend signs a short-lived HS256 JWT per request.
The user id is taken only from the token's `sub` claim.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

INTERNAL_TOKEN_AUDIENCE = "discipline-py"
INTERNAL_TOKEN_ALGORITHM = "HS256"

_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing internal token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> int:
    """FastAPI dependency: verify the internal JWT and return the user id from `sub`."""
    if credentials is None:
        raise _unauthorized()
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.INTERNAL_JWT_SECRET,
            algorithms=[INTERNAL_TOKEN_ALGORITHM],
            audience=INTERNAL_TOKEN_AUDIENCE,
            options={"require": ["exp", "aud", "sub"]},
        )
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError):
        raise _unauthorized() from None
    if user_id <= 0:
        raise _unauthorized()
    return user_id
