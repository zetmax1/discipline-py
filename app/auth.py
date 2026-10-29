"""
Internal authentication: the Go backend signs a short-lived HS256 JWT per request.
The user id is taken only from the token's `sub` claim and the user's IANA time
zone from its `tz` claim.
"""

from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    tz: str


def _valid_zone(name) -> bool:
    if not isinstance(name, str) or not name:
        return False
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
    return True


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """FastAPI dependency: verify the internal JWT and return the user it names."""
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
    tz = claims.get("tz")
    if user_id <= 0 or not _valid_zone(tz):
        raise _unauthorized()
    return CurrentUser(user_id=user_id, tz=tz)


def get_current_user_id(user: CurrentUser = Depends(get_current_user)) -> int:
    """The authenticated user's id (from the token's `sub`)."""
    return user.user_id


def get_current_tz(user: CurrentUser = Depends(get_current_user)) -> str:
    """The authenticated user's IANA time zone (from the token's `tz`)."""
    return user.tz
