"""How an OData client signs in (phase 24, D433).

* Bearer: the usual Keycloak access token (eax.auth.current_user), as every other call. Anything machine access (phase 25)
  adds to eax.auth for bearer credentials works here too.
* Basic: a user name and password, which is what Power BI and Excel offer for an OData feed. The password is never kept:
  Keycloak checks it (the eax-odata client, password grant only, D433) and the token it gives is then read like any
  other. The answer is remembered for a few minutes (by user name and a hash of the password) so a refresh that asks for
  many pages does not ask Keycloak each time.
* CHECKS: phase 25 (machine access) adds functions here that take (user name, secret) and give an auth.User for its own
  credentials (an API key or a personal token sent as the password), or None to let the next check try. They run before
  Keycloak is asked.

Every way gives the person's own EA Explorer roles: the feed reads only what they may read.
"""

from __future__ import annotations

import base64
import hashlib
import threading
import time
from collections.abc import Callable

from flask import g, request
from flask_smorest import abort

from . import auth, permissions
from .config import get_settings

CLIENT_ID = "eax-odata"
CACHE_SECONDS = 240
CHECKS: list[Callable[[str, str], auth.User | None]] = []

_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def _key(username: str, password: str) -> str:
    return hashlib.sha256(f"{username.lower()}\0{password}".encode()).hexdigest()


def _keycloak_claims(username: str, password: str) -> dict | None:
    """Asks Keycloak for a token with the person's user name and password; None when Keycloak says no."""
    import json
    import urllib.error
    import urllib.parse
    import urllib.request
    s = get_settings()
    url = f"{s.keycloak_internal_url}/realms/{s.realm}/protocol/openid-connect/token"
    body = urllib.parse.urlencode({"grant_type": "password", "client_id": CLIENT_ID, "username": username, "password": password,
                                   "scope": "openid"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=10) as r:
            token = json.loads(r.read()).get("access_token") or ""
    except urllib.error.HTTPError:
        return None
    except (urllib.error.URLError, OSError):
        abort(503, message="Sign-in is not answering just now; try again in a minute.")
    try:
        return auth.decode_token(token)
    except Exception:  # noqa: BLE001 - asked over the internal network: Keycloak may write its internal issuer
        import jwt
        signing_key = auth._jwks_client().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, signing_key, algorithms=["RS256"], audience=s.api_audience,
                            options={"require": ["exp", "iat", "iss"], "verify_iss": False}, leeway=30)
        internal = f"{s.keycloak_internal_url}/realms/{s.realm}"
        if claims.get("iss") not in [*s.accepted_issuers, internal]:
            return None
        return claims


def _basic(header: str) -> auth.User:
    try:
        username, _, password = base64.b64decode(header.split(" ", 1)[1].strip()).decode("utf-8").partition(":")
    except Exception:  # noqa: BLE001
        abort(401, message="Basic sign-in: send a user name and password.")
    if not username or not password:
        abort(401, message="Basic sign-in: send a user name and password.")
    for check in CHECKS:                        # machine access (phase 25): API keys and tokens
        user = check(username, password)
        if user is not None:
            return user
    key, now = _key(username, password), time.monotonic()
    with _lock:
        hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_SECONDS:
        claims = hit[1]
    else:
        claims = _keycloak_claims(username, password)
        if claims is None:
            abort(401, message="That user name and password were not accepted.")
        with _lock:
            _cache[key] = (now, claims)
            for k in [k for k, (t, _c) in _cache.items() if now - t > CACHE_SECONDS]:
                _cache.pop(k, None)
    return auth.user_from_claims(claims)


def user() -> auth.User:
    """The person calling the feed (Bearer or Basic); 401 with a Basic challenge so Excel and Power BI ask."""
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return auth.current_user()
    if header.lower().startswith("basic "):
        u = _basic(header)
        g.username = u.username
        return u
    abort(401, message="Sign in: Basic (your EA Explorer user name and password) or a Bearer access token.")


def signed_in(view: Callable) -> Callable:
    """Decorator: the call runs as the person (row-level security reads only their models)."""
    from functools import wraps

    @wraps(view)
    def wrapper(*args, **kwargs):
        u = user()
        g.user = u
        token = permissions.current.set(permissions.Principal(u.username, tuple(u.roles), u.break_glass))
        try:
            return view(*args, **kwargs)
        finally:
            permissions.current.reset(token)
    return wrapper
