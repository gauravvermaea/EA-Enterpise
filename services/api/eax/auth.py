"""Sign-in: every protected call carries an access token (OIDC bearer token).

Normally a Keycloak token, checked against Keycloak's signing keys (fetched over the internal
network), the issuer (the public Keycloak address) and the audience "eax-api". People are given
roles in Keycloak; the token's Keycloak roles are turned into EA Explorer roles through
core.role_mappings (permissions.py, D92).

When Keycloak is down, the break-glass account (D80) signs in through the API instead
(api/break_glass.py) and gets a short-lived token signed by the API itself, with the Super Admin
role. Every call it makes is audited.

Machine access (phase 25, D366): a token or API key (eaxt_..., eaxk_...) or a trusted client certificate signs a call in
as its owner, limited to the credential's areas (eax/machine_access.py). Every route that uses current_user() or
require_auth() takes them, the OData feed and reports included; the MCP server checks them the same way.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache, wraps

import jwt
from flask import g, request
from flask_smorest import abort

from . import permissions, reports
from .config import get_settings

BREAK_GLASS_ISSUER = "eaexplorer-break-glass"
BREAK_GLASS_USER = "break-glass"
# A break-glass session does not expire (D100): it lasts until the person signs out or the break-glass
# password is changed (the signing key comes from the password, so changing it ends every session).


@dataclass
class User:
    username: str
    email: str | None = None
    name: str | None = None
    roles: list[str] = field(default_factory=list)            # EA Explorer global roles (mapped from Keycloak)
    keycloak_roles: list[str] = field(default_factory=list)   # as Keycloak gave them
    break_glass: bool = False
    machine: object | None = None                              # the machine credential that signed the call in (phase 25)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def can(self, permission: str, model_roles=None) -> bool:
        return permissions.allowed(self.roles, permission, model_roles)


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(get_settings().jwks_url, cache_keys=True, lifespan=3600)


def break_glass_key() -> bytes | None:
    """The key break-glass tokens are signed with: derived from the break-glass password, so changing
    the password ends every break-glass session. None when no break-glass password is set."""
    secret = get_settings().break_glass_password
    if not secret:
        return None
    return hashlib.sha256(b"eaexplorer-break-glass:" + secret.encode()).digest()


def make_break_glass_token() -> str:
    key = break_glass_key()
    if not key:
        raise RuntimeError("no break-glass password set")
    now = int(time.time())
    return jwt.encode({"iss": BREAK_GLASS_ISSUER, "aud": get_settings().api_audience, "sub": BREAK_GLASS_USER,
                       "preferred_username": BREAK_GLASS_USER, "name": "Break-glass account",
                       "iat": now, "eax_break_glass": True},
                      key, algorithm="HS256")


def decode_token(token: str, *, key=None) -> dict:
    settings = get_settings()
    if jwt.get_unverified_header(token).get("alg") == "HS256":
        bg = break_glass_key()
        if not bg:
            raise jwt.InvalidTokenError("break-glass sign-in is not set up")
        return jwt.decode(token, bg, algorithms=["HS256"], audience=settings.api_audience,
                          issuer=BREAK_GLASS_ISSUER, options={"require": ["iat", "iss"]})
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


def user_from_claims(claims: dict, mapping: dict[str, set[str]] | None = None) -> User:
    if claims.get("eax_break_glass") and claims.get("iss") == BREAK_GLASS_ISSUER:
        return User(username=BREAK_GLASS_USER, name="Break-glass account", roles=[permissions.SUPER_ADMIN],
                    break_glass=True)
    kc_roles = sorted(claims.get("realm_access", {}).get("roles", []))
    # directory groups (Active Directory through Keycloak's LDAP federation, or Entra ID group claims; phase 36, D503):
    # the "groups" claim, each group mapped like a role under the key "group:<name>"
    groups = permissions.group_keys(claims.get("groups"))
    return User(
        username=(claims.get("preferred_username") or claims.get("sub", "unknown")).lower(),
        email=claims.get("email"),
        name=claims.get("name"),
        roles=permissions.app_roles([*kc_roles, *groups], mapping),
        keycloak_roles=kc_roles,
    )


def machine_user(kind: str, value: str) -> User:
    """A call signed in with a machine credential (phase 25): its owner, with the roles they have now, limited to its areas."""
    from . import machine_access as ma
    from .db import get_engine
    try:
        with get_engine().connect() as conn:
            machine, roles = ma.authenticate(conn, kind, value)
    except ma.Refused as exc:
        abort(exc.status, message=exc.message)
    why = machine.refusal(request.method, request.path)
    g.machine = machine                      # last used and the change log after the call (app.py)
    if why:
        g.machine_status = 403
        abort(403, message=why)
    return User(username=machine.owner, name=f"{machine.name} ({ma.KINDS[machine.kind].lower()})", roles=list(roles),
                machine=machine)


def current_user() -> User:
    header = request.headers.get("Authorization", "")
    bearer = header.split(" ", 1)[1].strip() if header.lower().startswith("bearer ") else None
    from . import machine_access as ma
    shown = ma.presented(request.headers, bearer)
    if shown:
        user = machine_user(*shown)
        g.username = user.username
        return user
    if not header.lower().startswith("bearer "):
        abort(401, message="Sign in required: send a Keycloak access token as a Bearer token.")
    try:
        claims = decode_token(header.split(" ", 1)[1].strip())
    except jwt.PyJWTError as exc:
        abort(401, message=f"Invalid token: {exc}")
    user = user_from_claims(claims)
    g.username = user.username
    return user


def _audit_break_glass(user: User) -> None:
    from . import audit
    from .db import get_engine
    with get_engine().begin() as conn:
        audit.record(conn, actor=user.username, action="break-glass.request", object_type="api",
                     object_id=request.path, source="api", request_id=getattr(g, "request_id", None),
                     details={"method": request.method})


def _test_lock(user: User) -> None:
    """A self-test in progress: a normal person's changes are refused (R2.51, D609); admins and the test go on."""
    from . import test_lock
    if test_lock.exempt(user.username, user.roles):
        return
    from .testing import store
    try:
        with store.engine().connect() as conn:       # the tests database (R2.28)
            run = test_lock.active(conn)
    except Exception:  # noqa: BLE001 - no test tables yet (a first start): nothing to wait for
        return
    if run:
        abort(423, **test_lock.refusal(run))


def require_auth(permission: str | None = None) -> Callable:
    """Decorator: the caller must be signed in and, when `permission` is given, allowed it: a global
    permission by their global roles; a model permission (model.*) by their role on the model in the
    view's `model_id` (or a global role that gives it on every model). The person is set for the
    database for the whole call."""

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            g.user = user
            reports.note_user(user.username, user.roles)   # who is who, for the reports' model access (D138)
            token = permissions.current.set(permissions.Principal(user.username, tuple(user.roles), user.break_glass))
            try:
                if permission:
                    mine: list[str] = []
                    if permission in permissions.MODEL_PERMISSIONS and kwargs.get("model_id") is not None \
                            and not user.can(permission):
                        from .db import get_engine
                        with get_engine().connect() as conn:
                            mine = permissions.model_roles(conn, user.username, kwargs["model_id"])
                    if not user.can(permission, mine):
                        abort(403, message=f"Not allowed: '{permission}' needs "
                                           + ("a role on this model that gives it "
                                              f"(yours: {', '.join(mine) or 'none'})" if permission in permissions.MODEL_PERMISSIONS
                                              else f"a global role that gives it (yours: {', '.join(user.roles) or 'none'})")
                                           + ".")
                if user.break_glass:
                    _audit_break_glass(user)
                if request.method not in ("GET", "HEAD", "OPTIONS"):
                    _test_lock(user)
                return view(*args, **kwargs)
            finally:
                permissions.current.reset(token)

        return wrapper

    return decorator
