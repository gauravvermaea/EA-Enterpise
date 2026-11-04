"""Sign-in: every protected call carries a Keycloak access token (OIDC bearer token).

Tokens are checked against Keycloak's signing keys (fetched over the internal network), the
issuer (the public Keycloak address) and the audience "eax-api".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache, wraps

import jwt
from flask import g, request
from flask_smorest import abort

from .config import get_settings


@dataclass
class User:
    username: str
    email: str | None = None
    name: str | None = None
    roles: list[str] = field(default_factory=list)

    def has_role(self, role: str) -> bool:
        return role in self.roles


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(get_settings().jwks_url, cache_keys=True, lifespan=3600)


def decode_token(token: str, *, key=None) -> dict:
    settings = get_settings()
    signing_key = key if key is not None else _jwks_client().get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        audience=settings.api_audience,
        options={"require": ["exp", "iat", "iss"], "verify_iss": False},
        leeway=30,
    )
    if claims.get("iss") not in settings.accepted_issuers:
        raise jwt.InvalidIssuerError(f"unexpected issuer {claims.get('iss')}")
    return claims


def user_from_claims(claims: dict) -> User:
    return User(
        username=claims.get("preferred_username") or claims.get("sub", "unknown"),
        email=claims.get("email"),
        name=claims.get("name"),
        roles=sorted(claims.get("realm_access", {}).get("roles", [])),
    )


def current_user() -> User:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        abort(401, message="Sign in required: send a Keycloak access token as a Bearer token.")
    try:
        claims = decode_token(header.split(" ", 1)[1].strip())
    except jwt.PyJWTError as exc:
        abort(401, message=f"Invalid token: {exc}")
    user = user_from_claims(claims)
    g.username = user.username
    return user


def require_auth(role: str | None = None) -> Callable:
    """Decorator: the caller must be signed in, and hold `role` when one is given."""

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if role and not user.has_role(role) and not user.has_role("system-admin"):
                abort(403, message=f"This needs the role '{role}'.")
            g.user = user
            return view(*args, **kwargs)

        return wrapper

    return decorator
