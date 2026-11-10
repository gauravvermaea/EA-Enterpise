"""Machine access (phase 25, D366, D378, D438 to D441): how other systems, scripts and MCP clients sign in without a person
at a browser.

Three kinds of credential, each belonging to a person (their own) or to a service account (made by a Super Admin or IT
Admin), each with an expiry, revoke, last used and every call in the change log:
  * a **token**: `Authorization: Bearer eaxt_...` (scripts, MCP clients, the OData feed in Excel and Power BI)
  * an **API key**: `X-API-Key: eaxk_...` (other systems; also accepted as a bearer token)
  * a **client certificate**: mutual TLS on the machine-access port of the proxy (EAX_MTLS_PORT, default 9443). The
    proxy asks for a certificate there only, accepts any (self-signed too) and passes it on; the API trusts a
    certificate only when a Super Admin or IT Admin uploaded that very certificate (its SHA-256 fingerprint, D378).

Each credential says **read or read-write per API area** (AREAS); an area left out is refused. Read means GET (and HEAD
or OPTIONS); anything else is a write. It can be limited to some models or projects: a call whose address is about
another model or project is refused (lists still show what the owner sees). It never gives more than its owner's roles:
a person's credential acts with the global roles the API last saw that person sign in with (core.known_users) and their
model roles; a service account with the global roles it was given and its model roles.

Secrets are shown once and kept only as a SHA-256 hash. Nothing of this is in the database's logic (D248).
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from . import permissions as perms

TOKEN_PREFIX, KEY_PREFIX = "eaxt_", "eaxk_"
KINDS = {"token": "Token", "api_key": "API key", "certificate": "Client certificate"}
# the longest a credential may live, and what a new one gets unless asked (days)
MAX_DAYS = {"token": 365, "api_key": 730, "certificate": 730}
DEFAULT_DAYS = {"token": 90, "api_key": 365, "certificate": 365}
CERT_HEADER = "X-EAX-Client-Cert"        # set by the proxy on the machine-access port only (url-escaped PEM)

# The API areas (D366), with the addresses each holds (the first match wins; tested in tests/test_machine_access.py)
AREAS: list[tuple[str, str, str]] = [
    ("models", "Models and content", "models, entities, relationships, changes and commits, tags, views, sheets and loads, search"),
    ("metamodel", "Metamodel", "entity and relationship types, attributes, rules, metamodel versions, drafts and push-down"),
    ("projects", "Projects", "architecture projects, their steps, governance, the repository, tracking sheets, calendars"),
    ("documents", "Documents", "project documents and files, change documents"),
    ("reports", "Reports", "reports, quality, comparisons, gap analyses, common analysis, maps, KPI trends, the OData feed"),
    ("library", "Library", "the model library, the project library and the reference library"),
    ("change_log", "Change log", "the change log"),
    ("administration", "Administration", "settings, users and roles, backups, jobs, the audit log, operations, metrics"),
    ("mcp", "MCP", "the MCP server (/mcp)"),
]
AREA_CODES = [a for a, *_ in AREAS]
LEVELS = ("read", "read-write")

_M = r"models/[^/]+/"
_RULES: list[tuple[str, str]] = [
    (r"^/mcp(/|$)", "mcp"),
    (r"^/api/v1/change-log(/|$)", "change_log"),
    (r"^/api/v1/(admin|audit|sql|jobs|keycloak-roles|role-mappings|roles|settings|startup|internal|machine-access|"
     r"operations|break-glass)(/|$)", "administration"),
    (r"^/api/metrics$", "administration"),
    (r"^/api/v1/(reference-library|models/library|projects/library|projects/reference-sources)(/|$)", "library"),
    (r"^/api/v1/projects/[^/]+/(library|reference)(/|$)", "library"),
    (r"^/api/v1/projects/[^/]+/(documents|files)(/|$)", "documents"),
    (r"^/api/v1/projects/[^/]+/placeholder-views/files", "documents"),
    (r"^/api/v1/(change-documents|" + _M + r"change-documents)(/|$)", "documents"),
    (r"^/api/v1/(odata|kpis?|report-designer|reports)(/|$)", "reports"),
    (r"^/api/v1/(quality|compare|compare-profiles|gaps|gap-runs|commons|report-audiences)(/|$)", "reports"),
    (r"^/api/v1/" + _M + r"(reports|quality|heat-map|maps|kpis?|graph|tree/xlsx)(/|$)", "reports"),
    (r"^/api/v1/" + _M + r"(metamodel|metamodel-spec|entity-types|relationship-types|pushdown|extend|extend-preview|"
     r"grids/metamodel|tree/metamodel|tree/types)(/|$)", "metamodel"),
    (r"^/api/v1/(metamodel-drafts|metamodel-workbooks)(/|$)", "metamodel"),
    (r"^/api/v1/(projects|repository|tracking-sheets|calendars|calendar-feed|surveys|maturity)(/|$)", "projects"),
    (r"^/api/v1/", "models"),
]
_COMPILED = [(re.compile(p), a) for p, a in _RULES]
# calls any signed-in credential may make, whatever its areas: who am I, is it up
ALWAYS = (re.compile(r"^/api/v1/(me|heartbeat)/?$"),)
_MODEL_IN_PATH = re.compile(r"^/api/v1/models/([0-9a-f-]{36})(/|$)")
_PROJECT_IN_PATH = re.compile(r"^/api/v1/projects/([0-9a-f-]{36})(/|$)")


def area_of(path: str) -> str | None:
    """The API area an address belongs to, or None for addresses outside the areas (heartbeat, health, docs)."""
    for rx, area in _COMPILED:
        if rx.search(path):
            return area
    return None


def is_read(method: str) -> bool:
    return method.upper() in ("GET", "HEAD", "OPTIONS")


# ---------------------------------------------------------------- secrets and certificates
def new_secret(kind: str) -> str:
    return (TOKEN_PREFIX if kind == "token" else KEY_PREFIX) + secrets.token_urlsafe(30)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.strip().encode()).hexdigest()


def looks_like_secret(value: str) -> bool:
    v = (value or "").strip()
    return v.startswith((TOKEN_PREFIX, KEY_PREFIX)) and 20 <= len(v) <= 200


def cert_info(pem: str) -> dict:
    """The SHA-256 fingerprint, subject and expiry of a PEM certificate (raises ValueError when it is not one)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import Encoding
    try:
        cert = x509.load_pem_x509_certificate(pem.strip().encode())
    except Exception as exc:  # noqa: BLE001 - whatever the library says, the answer is the same
        raise ValueError("That is not a PEM certificate (-----BEGIN CERTIFICATE----- ...).") from exc
    not_after = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after.replace(tzinfo=UTC)
    return {"fingerprint": cert.fingerprint(hashes.SHA256()).hex(), "subject": cert.subject.rfc4514_string(),
            "not_after": not_after, "pem": cert.public_bytes(Encoding.PEM).decode()}


def cert_from_header(value: str) -> str | None:
    """The PEM the proxy passed on ($ssl_client_escaped_cert), or None."""
    v = urllib.parse.unquote(value or "").strip()
    return v if v.startswith("-----BEGIN CERTIFICATE-----") else None


# ---------------------------------------------------------------- who a call is
@dataclass
class Machine:
    """A credential that signed a call in."""
    id: int
    guid: str
    owner: str
    kind: str
    name: str
    scopes: dict[str, str]
    model_guids: list[str] = field(default_factory=list)
    project_guids: list[str] = field(default_factory=list)
    service: bool = False

    def refusal(self, method: str, path: str) -> str | None:
        """Why this credential may not make this call, or None when it may."""
        if any(rx.search(path) for rx in ALWAYS):
            return None
        area = area_of(path)
        if area is None:
            return None
        level = self.scopes.get(area)
        label = dict((a, lab) for a, lab, _ in AREAS)[area]
        if not level:
            return f"This {KINDS[self.kind].lower()} ('{self.name}') has no access to {label}."
        if level == "read" and not is_read(method):
            return f"This {KINDS[self.kind].lower()} ('{self.name}') may only read {label}."
        m = _MODEL_IN_PATH.search(path)
        if m and self.model_guids and m.group(1) not in self.model_guids:
            return f"This {KINDS[self.kind].lower()} ('{self.name}') is limited to other models."
        p = _PROJECT_IN_PATH.search(path)
        if p and self.project_guids and p.group(1) not in self.project_guids:
            return f"This {KINDS[self.kind].lower()} ('{self.name}') is limited to other projects."
        return None


class Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _now() -> datetime:
    return datetime.now(UTC)


def _dt(v):
    """A timestamp as a timezone-aware datetime (drivers give datetimes; JSON gives text)."""
    if v is None or isinstance(v, datetime):
        return v if v is None or v.tzinfo else v.replace(tzinfo=UTC)
    d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def presented(headers, bearer: str | None) -> tuple[str, str] | None:
    """What a call presents, if it is machine access: ("secret", value) or ("certificate", pem)."""
    key = (headers.get("X-API-Key") or "").strip()
    if key:
        return ("secret", key)
    if bearer and looks_like_secret(bearer):
        return ("secret", bearer)
    pem = cert_from_header(headers.get(CERT_HEADER) or "")
    if pem and not bearer:
        return ("certificate", pem)
    return None


def authenticate(conn, kind: str, value: str) -> tuple[Machine, tuple[str, ...]]:
    """The credential and the global roles it acts with; raises Refused (401 or 403) with why."""
    if kind == "secret":
        row = conn.execute(text("SELECT * FROM core.machine_credentials WHERE secret_hash = :h"),
                           {"h": hash_secret(value)}).mappings().first()
    else:
        try:
            fp = cert_info(value)["fingerprint"]
        except ValueError:
            raise Refused(401, "The client certificate could not be read.") from None
        row = conn.execute(text("SELECT * FROM core.machine_credentials WHERE cert_fingerprint = :f"),
                           {"f": fp}).mappings().first()
    if not row:
        raise Refused(401, "Unknown credential." if kind == "secret"
                      else "This client certificate is not trusted: a Super Admin or IT Admin uploads it on "
                           "System admin > Machine access.")
    row = dict(row)
    what = f"{KINDS[row['kind']]} '{row['name']}'"
    if row["revoked_at"]:
        raise Refused(401, f"{what} was revoked.")
    expires = _dt(row["expires_at"])
    if expires and expires <= _now():
        raise Refused(401, f"{what} expired on {expires:%Y-%m-%d}.")
    roles = owner_roles(conn, row["owner"])
    if roles is None:
        raise Refused(403, f"{what} belongs to {row['owner']}, who is disabled or not known here.")
    scopes = row["scopes"] if isinstance(row["scopes"], dict) else json.loads(row["scopes"] or "{}")
    return (Machine(id=row["id"], guid=str(row["guid"]), owner=row["owner"], kind=row["kind"], name=row["name"],
                    scopes=scopes, model_guids=[str(x) for x in row["model_guids"] or []],
                    project_guids=[str(x) for x in row["project_guids"] or []],
                    service=row["owner"].startswith("svc-")), tuple(roles))


def owner_roles(conn, owner: str) -> list[str] | None:
    """The global roles a credential's owner acts with now (never more than they have), or None when they may not."""
    if owner.startswith("svc-"):
        r = conn.execute(text("SELECT roles, disabled_at FROM core.service_accounts WHERE username = :u"),
                         {"u": owner}).mappings().first()
        if not r or r["disabled_at"]:
            return None
        return [x for x in r["roles"] if x in perms.GLOBAL_ROLES]
    r = conn.execute(text("SELECT roles FROM core.known_users WHERE username = :u"), {"u": owner}).mappings().first()
    if not r:
        return None
    return [x for x in r["roles"] if x in perms.GLOBAL_ROLES]


def note_use(conn, machine: Machine, method: str, path: str, status: int, source: str, request_id: str | None) -> None:
    """Last used, and the call in the audit trail and so the change log (D366)."""
    conn.execute(text("""UPDATE core.machine_credentials SET last_used_at = now(), last_used_from = :f, last_used_path = :p,
                                use_count = use_count + 1 WHERE id = :i"""),
                 {"f": (source or "")[:100], "p": f"{method} {path}"[:300], "i": machine.id})
    from . import audit
    audit.record(conn, actor=machine.owner, action="machine.call", object_type="credential", object_id=machine.guid,
                 source="machine", request_id=request_id,
                 details={"name": machine.name, "kind": machine.kind, "method": method, "path": path[:300],
                          "status": status, "area": area_of(path), "from": source})


# ---------------------------------------------------------------- managing credentials
def can_manage_all(roles) -> bool:
    """Super Admins and IT Admins see and revoke every credential and make service accounts (D366)."""
    return bool(set(roles or []) & {perms.SUPER_ADMIN, perms.IT_ADMIN})


def clean_scopes(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError("Say which areas it may use: {area: read | read-write}.")
    out = {}
    for area, level in raw.items():
        if not level or level == "none":
            continue
        if area not in AREA_CODES:
            raise ValueError(f"Unknown area '{area}': one of {', '.join(AREA_CODES)}.")
        if level not in LEVELS:
            raise ValueError(f"Area '{area}': read or read-write, not '{level}'.")
        out[area] = level
    if not out:
        raise ValueError("Give it at least one area.")
    return out


def _guids(conn, table: str, values: Any) -> list[str]:
    if not values:
        return []
    vals = [str(v) for v in values]
    found = {str(r["guid"]) for r in conn.execute(text(f"SELECT guid FROM {table} WHERE guid::text = ANY(:g)"),
                                                   {"g": vals}).mappings()}
    missing = [v for v in vals if v not in found]
    if missing:
        raise ValueError(f"Not found: {', '.join(missing)}.")
    return vals


def create(conn, actor: str, actor_roles, body: dict) -> dict:
    """A new credential. Returns it, with the secret once (tokens and API keys)."""
    kind = body.get("kind")
    if kind not in KINDS:
        raise ValueError("kind: token, api_key or certificate.")
    owner = (body.get("owner") or actor).strip().lower()
    manage_all = can_manage_all(actor_roles)
    if owner != actor.lower():
        if not owner.startswith("svc-") or not manage_all:
            raise PermissionError("Only Super Admins and IT Admins make credentials for service accounts; "
                                  "people make their own.")
        sa = conn.execute(text("SELECT disabled_at FROM core.service_accounts WHERE username = :u"),
                          {"u": owner}).mappings().first()
        if not sa:
            raise ValueError(f"No service account {owner}.")
        if sa["disabled_at"]:
            raise ValueError(f"{owner} is disabled.")
    if kind == "certificate" and not manage_all:
        raise PermissionError("Client certificates are uploaded by Super Admins and IT Admins (D378).")
    name = (body.get("name") or "").strip()
    if not name:
        raise ValueError("Give it a name: what uses it.")
    days = int(body.get("days") or DEFAULT_DAYS[kind])
    if not 1 <= days <= MAX_DAYS[kind]:
        raise ValueError(f"A {KINDS[kind].lower()} lives 1 to {MAX_DAYS[kind]} days.")
    expires = _now() + timedelta(days=days)
    scopes = clean_scopes(body.get("scopes"))
    models = _guids(conn, "core.models", body.get("model_guids"))
    projects = _guids(conn, "proj.projects", body.get("project_guids"))
    secret, cert = None, None
    if kind == "certificate":
        cert = cert_info(body.get("pem") or "")
        if cert["not_after"] < expires:
            expires = cert["not_after"]
        if expires <= _now():
            raise ValueError("That certificate has expired.")
        if conn.execute(text("SELECT 1 FROM core.machine_credentials WHERE cert_fingerprint = :f"),
                        {"f": cert["fingerprint"]}).first():
            raise ValueError("That certificate is uploaded already.")
    else:
        secret = new_secret(kind)
    row = conn.execute(text("""
        INSERT INTO core.machine_credentials (owner, kind, name, secret_prefix, secret_hash, cert_fingerprint, cert_subject,
               cert_not_after, cert_pem, scopes, model_guids, project_guids, expires_at, created_by)
        VALUES (:o, :k, :n, :sp, :sh, :cf, :cs, :cn, :cp, CAST(:sc AS jsonb), CAST(:mg AS uuid[]), CAST(:pg AS uuid[]), :e, :by)
        RETURNING id"""), {"o": owner, "k": kind, "n": name[:120], "sp": secret[:12] if secret else "",
                           "sh": hash_secret(secret) if secret else None, "cf": cert and cert["fingerprint"],
                           "cs": cert["subject"] if cert else "", "cn": cert and cert["not_after"], "cp": cert["pem"] if cert else "",
                           "sc": json.dumps(scopes), "mg": "{" + ",".join(models) + "}", "pg": "{" + ",".join(projects) + "}",
                           "e": expires, "by": actor}).mappings().one()
    from . import audit
    out = get(conn, row["id"])
    audit.record(conn, actor=actor, action="machine.credential.create", object_type="credential", object_id=out["guid"],
                 details={"name": name, "kind": kind, "owner": owner, "scopes": scopes, "expires_at": out["expires_at"]})
    if secret:
        out["secret"] = secret
        out["use"] = (f"Authorization: Bearer {secret}" if kind == "token" else f"X-API-Key: {secret}")
    return out


def _shape(r: dict) -> dict:
    now = _now()
    r = {**r, **{k: _dt(r[k]) for k in ("expires_at", "created_at", "revoked_at", "last_used_at")}}
    state = ("revoked" if r["revoked_at"] else "expired" if r["expires_at"] <= now
             else "expiring" if r["expires_at"] <= now + timedelta(days=14) else "active")
    scopes = r["scopes"] if isinstance(r["scopes"], dict) else json.loads(r["scopes"] or "{}")
    return {"id": r["id"], "guid": str(r["guid"]), "owner": r["owner"], "service": r["owner"].startswith("svc-"),
            "kind": r["kind"], "kind_label": KINDS[r["kind"]], "name": r["name"], "prefix": r["secret_prefix"],
            "fingerprint": r["cert_fingerprint"] or "", "subject": r["cert_subject"], "scopes": scopes,
            "model_guids": [str(x) for x in r["model_guids"] or []], "project_guids": [str(x) for x in r["project_guids"] or []],
            "expires_at": r["expires_at"].isoformat(), "created_by": r["created_by"], "created_at": r["created_at"].isoformat(),
            "revoked_at": r["revoked_at"] and r["revoked_at"].isoformat(), "revoked_by": r["revoked_by"],
            "revoke_reason": r["revoke_reason"], "last_used_at": r["last_used_at"] and r["last_used_at"].isoformat(),
            "last_used_from": r["last_used_from"], "last_used_path": r["last_used_path"], "use_count": r["use_count"],
            "state": state}


def get(conn, ident) -> dict:
    r = conn.execute(text("SELECT * FROM core.machine_credentials WHERE id::text = :i OR guid::text = :i"),
                     {"i": str(ident)}).mappings().first()
    if not r:
        raise LookupError("No such credential.")
    return _shape(dict(r))


def listing(conn, actor: str, actor_roles, everyone: bool = False) -> list[dict]:
    """A person's own credentials; with everyone (Super Admins and IT Admins) every one, service accounts' too."""
    if everyone and can_manage_all(actor_roles):
        rows = conn.execute(text("SELECT * FROM core.machine_credentials ORDER BY revoked_at IS NOT NULL, owner, created_at DESC"))
    else:
        rows = conn.execute(text("""SELECT * FROM core.machine_credentials WHERE owner = lower(:u)
                                     ORDER BY revoked_at IS NOT NULL, created_at DESC"""), {"u": actor})
    return [_shape(dict(r)) for r in rows.mappings()]


def revoke(conn, actor: str, actor_roles, ident, reason: str = "") -> dict:
    c = get(conn, ident)
    if c["owner"] != actor.lower() and not can_manage_all(actor_roles):
        raise PermissionError("Only its owner, a Super Admin or an IT Admin revokes it.")
    if c["revoked_at"]:
        return c
    conn.execute(text("UPDATE core.machine_credentials SET revoked_at = now(), revoked_by = :a, revoke_reason = :r WHERE id = :i"),
                 {"a": actor, "r": (reason or "")[:300], "i": c["id"]})
    from . import audit
    audit.record(conn, actor=actor, action="machine.credential.revoke", object_type="credential", object_id=c["guid"],
                 details={"name": c["name"], "kind": c["kind"], "owner": c["owner"], "reason": reason})
    return get(conn, c["id"])


def change(conn, actor: str, actor_roles, ident, body: dict) -> dict:
    """Areas, limits, name or a shorter expiry; a longer one means a new credential."""
    c = get(conn, ident)
    if c["owner"] != actor.lower() and not can_manage_all(actor_roles):
        raise PermissionError("Only its owner, a Super Admin or an IT Admin changes it.")
    if c["revoked_at"]:
        raise ValueError("It is revoked.")
    sets, params = [], {"i": c["id"]}
    if "name" in body:
        sets.append("name = :n")
        params["n"] = (body["name"] or c["name"]).strip()[:120]
    if "scopes" in body:
        sets.append("scopes = CAST(:sc AS jsonb)")
        params["sc"] = json.dumps(clean_scopes(body["scopes"]))
    if "model_guids" in body:
        sets.append("model_guids = CAST(:mg AS uuid[])")
        params["mg"] = "{" + ",".join(_guids(conn, "core.models", body["model_guids"])) + "}"
    if "project_guids" in body:
        sets.append("project_guids = CAST(:pg AS uuid[])")
        params["pg"] = "{" + ",".join(_guids(conn, "proj.projects", body["project_guids"])) + "}"
    if body.get("expires_at"):
        new = datetime.fromisoformat(str(body["expires_at"]).replace("Z", "+00:00"))
        if new.tzinfo is None:
            new = new.replace(tzinfo=UTC)
        if new > _dt(c["expires_at"]):
            raise ValueError("An expiry can only be brought forward; make a new credential for longer.")
        sets.append("expires_at = :e")
        params["e"] = new
    if sets:
        conn.execute(text(f"UPDATE core.machine_credentials SET {', '.join(sets)} WHERE id = :i"), params)
        from . import audit
        audit.record(conn, actor=actor, action="machine.credential.change", object_type="credential", object_id=c["guid"],
                     details={"name": c["name"], **{k: body[k] for k in ("name", "scopes", "model_guids", "project_guids",
                                                                        "expires_at") if k in body}})
    return get(conn, c["id"])


# ---------------------------------------------------------------- service accounts
SERVICE_ROLES = [perms.USER, perms.MODEL_CREATOR, perms.LIBRARY_ADMIN, perms.IT_ADMIN, perms.SUPER_ADMIN]


def service_accounts(conn) -> list[dict]:
    rows = conn.execute(text("""
        SELECT s.*, (SELECT count(*) FROM core.machine_credentials c WHERE c.owner = s.username
                       AND c.revoked_at IS NULL AND c.expires_at > now()) AS live_credentials,
               (SELECT max(c.last_used_at) FROM core.machine_credentials c WHERE c.owner = s.username) AS last_used_at,
               (SELECT coalesce(json_agg(json_build_object('model', m.name, 'guid', m.guid, 'role', u.role) ORDER BY m.name), '[]')
                  FROM core.model_users u JOIN core.models m ON m.id = u.model_id WHERE u.username = s.username) AS model_roles
          FROM core.service_accounts s ORDER BY s.disabled_at IS NOT NULL, s.username""")).mappings()
    out = []
    for r in rows:
        mr = r["model_roles"] if isinstance(r["model_roles"], list) else json.loads(r["model_roles"] or "[]")
        iso = (lambda v: _dt(v).isoformat() if v else None)
        out.append({"guid": str(r["guid"]), "username": r["username"], "name": r["name"], "description": r["description"],
                    "roles": list(r["roles"]), "created_by": r["created_by"], "created_at": iso(r["created_at"]),
                    "disabled_at": iso(r["disabled_at"]), "disabled_by": r["disabled_by"],
                    "live_credentials": r["live_credentials"], "model_roles": mr, "last_used_at": iso(r["last_used_at"])})
    return out


def _check_roles(roles: Any, actor_roles) -> list[str]:
    roles = [r for r in (roles or [perms.USER])]
    bad = [r for r in roles if r not in SERVICE_ROLES]
    if bad:
        raise ValueError(f"A service account's global roles: {', '.join(SERVICE_ROLES)} (not {', '.join(bad)}).")
    if perms.SUPER_ADMIN in roles and perms.SUPER_ADMIN not in set(actor_roles or []):
        raise PermissionError("Only a Super Admin gives a service account the Super Admin role.")
    return sorted(set(roles), key=perms.APP_ROLES.index)


def create_service_account(conn, actor: str, actor_roles, body: dict) -> dict:
    if not can_manage_all(actor_roles):
        raise PermissionError("Service accounts are made by Super Admins and IT Admins.")
    raw = (body.get("username") or body.get("name") or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw.removeprefix("svc-")).strip("-")[:40]
    username = f"svc-{slug}"
    if len(slug) < 2:
        raise ValueError("Give it a name of at least two letters (it becomes svc-<name>).")
    if conn.execute(text("SELECT 1 FROM core.service_accounts WHERE username = :u"), {"u": username}).first():
        raise ValueError(f"{username} exists already.")
    roles = _check_roles(body.get("roles"), actor_roles)
    conn.execute(text("""INSERT INTO core.service_accounts (username, name, description, roles, created_by)
                          VALUES (:u, :n, :d, :r, :by)"""),
                 {"u": username, "n": (body.get("name") or username).strip()[:120], "d": (body.get("description") or "")[:500],
                  "r": roles, "by": actor})
    from . import audit
    audit.record(conn, actor=actor, action="machine.service_account.create", object_type="service_account",
                 object_id=username, details={"username": username, "roles": roles})
    return next(s for s in service_accounts(conn) if s["username"] == username)


def change_service_account(conn, actor: str, actor_roles, username: str, body: dict) -> dict:
    if not can_manage_all(actor_roles):
        raise PermissionError("Service accounts are changed by Super Admins and IT Admins.")
    sa = next((s for s in service_accounts(conn) if s["username"] == username), None)
    if not sa:
        raise LookupError(f"No service account {username}.")
    if perms.SUPER_ADMIN in sa["roles"] and perms.SUPER_ADMIN not in set(actor_roles or []):
        raise PermissionError("Only a Super Admin changes a Super Admin service account.")
    sets, params = [], {"u": username}
    if "roles" in body:
        sets.append("roles = :r")
        params["r"] = _check_roles(body["roles"], actor_roles)
    if "description" in body:
        sets.append("description = :d")
        params["d"] = (body["description"] or "")[:500]
    if "name" in body:
        sets.append("name = :n")
        params["n"] = (body["name"] or sa["name"]).strip()[:120]
    if "disabled" in body:
        if body["disabled"]:
            sets.append("disabled_at = coalesce(disabled_at, now()), disabled_by = coalesce(disabled_by, :a)")
        else:
            sets.append("disabled_at = NULL, disabled_by = NULL")
        params["a"] = actor
    if sets:
        conn.execute(text(f"UPDATE core.service_accounts SET {', '.join(sets)} WHERE username = :u"), params)
        from . import audit
        audit.record(conn, actor=actor, action="machine.service_account.change", object_type="service_account",
                     object_id=username, details={"username": username, **body})
    return next(s for s in service_accounts(conn) if s["username"] == username)


def areas(app_rules: list[tuple[str, str]] | None = None) -> list[dict]:
    """The areas with the addresses in each (from the API's own routes when given: [(methods, rule)])."""
    out = [{"code": c, "label": label, "holds": holds, "endpoints": []} for c, label, holds in AREAS]
    by = {a["code"]: a for a in out}
    for methods, rule in app_rules or []:
        a = area_of(re.sub(r"<[^>]+>", "x", rule))
        if a:
            by[a]["endpoints"].append({"methods": methods, "path": rule})
    return out



def odata_check(username: str, password: str):
    """The OData feed's Basic sign-in (Excel, Power BI; D433): a token or API key sent as the password (any user name)
    signs in as its owner, limited to its areas like any call. None lets the feed ask Keycloak instead."""
    if not looks_like_secret(password):
        return None
    from .auth import machine_user
    return machine_user("secret", password)
