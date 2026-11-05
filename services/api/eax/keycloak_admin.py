"""Reading people and roles from Keycloak (build phase 3.1).

Roles are given to people in Keycloak, never in EA Explorer (D92); when Active Directory comes, its
groups are also managed in Keycloak. EA Explorer only reads: the users, their effective realm roles
(direct, through composite roles and through groups) and the realm's roles, with the API's own
client `eax-admin` (client credentials; its service account may view users and the realm).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from threading import Lock

from .config import get_settings

_token: dict[str, object] = {"value": None, "until": 0.0}
_lock = Lock()
TIMEOUT = 5


class KeycloakError(RuntimeError):
    pass


def _base() -> str:
    s = get_settings()
    return s.keycloak_internal_url.rstrip("/")


def _service_token() -> str:
    s = get_settings()
    with _lock:
        if _token["value"] and time.monotonic() < float(_token["until"]):
            return str(_token["value"])
    if not s.admin_client_secret:
        raise KeycloakError("EAX_KC_SERVICE_SECRET is not set: the API cannot read users from Keycloak.")
    data = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": s.admin_client_id,
                                   "client_secret": s.admin_client_secret}).encode()
    url = f"{_base()}/realms/{s.realm}/protocol/openid-connect/token"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=TIMEOUT) as r:
            body = json.load(r)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise KeycloakError(f"Keycloak did not give the API a token: {exc}") from exc
    with _lock:
        _token.update(value=body["access_token"], until=time.monotonic() + max(10, int(body.get("expires_in", 60)) - 20))
    return body["access_token"]


def _get(path: str, **params) -> object:
    s = get_settings()
    query = ("?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})) if params else ""
    req = urllib.request.Request(f"{_base()}/admin/realms/{s.realm}{path}{query}",
                                 headers={"Authorization": f"Bearer {_service_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        raise KeycloakError(f"Keycloak refused {path}: {exc.code} {exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise KeycloakError(f"Keycloak is not reachable: {exc}") from exc


def realm_roles() -> list[dict]:
    """The realm's roles (name and description), Keycloak's own defaults left out."""
    skip = {"offline_access", "uma_authorization"}
    return sorted(({"name": r["name"], "description": r.get("description") or ""} for r in _get("/roles")
                   if r["name"] not in skip and not r["name"].startswith("default-roles-")), key=lambda r: r["name"])


def users(search: str | None = None, first: int = 0, limit: int = 100) -> list[dict]:
    """People in the realm with their effective realm roles."""
    out = []
    for u in _get("/users", search=search, first=first, max=limit, briefRepresentation="true"):
        roles = [r["name"] for r in _get(f"/users/{u['id']}/role-mappings/realm/composite")]
        out.append({"id": u["id"], "username": u.get("username", "").lower(), "email": u.get("email"),
                    "name": " ".join(x for x in (u.get("firstName"), u.get("lastName")) if x) or None,
                    "enabled": u.get("enabled", True), "keycloak_roles": sorted(roles)})
    return out


def console_url(user_id: str | None = None) -> str:
    """Where to give someone a role: the Keycloak admin console of this realm."""
    s = get_settings()
    base = f"{s.public_base_url}/auth/admin/{s.realm}/console/#/{s.realm}"
    return f"{base}/users/{user_id}/role-mapping" if user_id else f"{base}/roles"


def set_sessions(idle_seconds: int, max_seconds: int) -> None:
    """Phase 10 (D183): the session time-outs set in the administration console, written to the realm. Needs the
    service account's manage-realm role (deploy/keycloak/realm-eaexplorer.json.tmpl); only these two fields change."""
    s = get_settings()
    body = json.dumps({"ssoSessionIdleTimeout": int(idle_seconds), "ssoSessionMaxLifespan": int(max_seconds)}).encode()
    req = urllib.request.Request(f"{_base()}/admin/realms/{s.realm}", data=body, method="PUT",
                                 headers={"Authorization": f"Bearer {_service_token()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT):
            return
    except urllib.error.HTTPError as exc:
        raise KeycloakError(f"Keycloak refused the session time-outs: {exc.code} {exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise KeycloakError(f"Keycloak is not reachable: {exc}") from exc
