"""Who may do what (build phase 3.1, D58, D59, D60, D89, D90, D92, D96).

Two kinds of role:
  * Global roles, given in Keycloak: Super Admin, IT Admin, User Admin, Keycloak Admin, Global Model
    Admin, and User (everyone who may sign in). Keycloak roles map to them in core.role_mappings
    (eax-super-admin to super-admin and so on by default; any Keycloak role can be mapped).
  * Model roles, given per model in EA Explorer (core.model_users): Model Admin, Architect, Model Sub
    Admin, Report Viewer. One person can be Architect on one model and Model Admin on another.

This module holds the one permission check the REST API and the MCP server both use. The database
enforces the same rules again for every connection the API opens (the user and their global roles are
set on the connection in db.py; row-level security and triggers in migrations/sql/0006_roles.sql). The
checks here give a clear 403 first; the database is the guard.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock

from sqlalchemy import text

# global roles (Keycloak, D92, D96)
SUPER_ADMIN, IT_ADMIN, USER_ADMIN, KEYCLOAK_ADMIN = "super-admin", "it-admin", "user-admin", "keycloak-admin"
MODEL_CREATOR, USER = "model-creator", "user"
GLOBAL_ROLES = [SUPER_ADMIN, IT_ADMIN, USER_ADMIN, KEYCLOAK_ADMIN, MODEL_CREATOR, USER]
# model roles (per model, several allowed on one model)
MODEL_ADMIN, MODEL_SUB_ADMIN, ARCHITECT, REPORT_VIEWER = "model-admin", "model-sub-admin", "architect", "report-viewer"
MODEL_ROLES = [MODEL_ADMIN, MODEL_SUB_ADMIN, ARCHITECT, REPORT_VIEWER]   # highest first
APP_ROLES = GLOBAL_ROLES + MODEL_ROLES

# Global permissions: any one of these global roles (Super Admin always)
GLOBAL_PERMISSIONS: dict[str, set[str]] = {
    "system.operate": {IT_ADMIN},          # jobs, audit log, SQL window, backups
    "users.read": {USER_ADMIN},            # the Users page: people, roles, which models (Model Admins: see access.py)
    "roles.map": {USER_ADMIN},             # map Keycloak roles to global roles
    "keycloak.console": {KEYCLOAK_ADMIN},
    "models.all": set(),                   # read every model: Super Admin only
    "models.create": {MODEL_CREATOR},      # create a model and become its Model Admin (model creation: phase 4)
}
# Model permissions: the person's roles on that model
MODEL_PERMISSIONS: dict[str, set[str]] = {
    "model.read": {MODEL_ADMIN, ARCHITECT, MODEL_SUB_ADMIN, REPORT_VIEWER},
    "model.content": {MODEL_ADMIN, ARCHITECT, MODEL_SUB_ADMIN},   # D90: Model Admins too
    "model.metamodel": {MODEL_ADMIN},                              # D89
    "model.lock": {MODEL_ADMIN},
    "model.people": {MODEL_ADMIN},                                 # give people roles on the model
    "model.derive": {MODEL_ADMIN},                                 # create a child model (phase 4)
}
PERMISSIONS = {**GLOBAL_PERMISSIONS, **MODEL_PERMISSIONS}
SEES_EVERY_MODEL = {SUPER_ADMIN}

# Laptop only: test users (setup puts them in Keycloak, the seed gives their model roles, eax init/up/logins
# print them). (user name, Keycloak role, {model name or "*": [model roles]}). The Fynbos and Karoo models
# are laptop test models (eax/seed/build.py test_models_sql).
TEST_USERS = [
    ("user_super_admin", "eax-super-admin", {}),
    ("user_it_admin", "eax-it-admin", {}),
    ("user_keycloak_admin", "eax-keycloak-admin", {}),
    ("user_user_admin", "eax-user-admin", {}),
    ("user_model_creator", "eax-model-creator", {"Karoo Re (independent)": [MODEL_ADMIN], "Lean EA metamodel": [MODEL_ADMIN],
                                                 "Karoo Digital (lean)": [MODEL_ADMIN]}),
    ("user_model_admin", "eax-user", {"Fynbos Mutual (group)": [MODEL_ADMIN], "Fynbos Life": [MODEL_ADMIN],
                                      "Sample insurance model": [ARCHITECT]}),
    ("user_architect", "eax-user", {"Sample insurance model": [ARCHITECT], "Fynbos Life": [ARCHITECT],
                                    "Fynbos Commercial": [MODEL_SUB_ADMIN, REPORT_VIEWER]}),
    ("user_model_sub_admin", "eax-user", {"Sample insurance model": [MODEL_SUB_ADMIN], "Fynbos Life": [MODEL_SUB_ADMIN],
                                          "Fynbos Commercial": [MODEL_SUB_ADMIN], "Karoo Re (independent)": [MODEL_SUB_ADMIN]}),
    ("user_report_viewer", "eax-user", {"Fynbos Mutual (group)": [REPORT_VIEWER], "Sample insurance model": [REPORT_VIEWER]}),
    ("user_global_architect", "eax-user", {"*": [ARCHITECT]}),
]


@dataclass(frozen=True)
class Principal:
    """The signed-in person as the database is told: user name and global roles."""
    username: str
    roles: tuple[str, ...] = field(default_factory=tuple)
    break_glass: bool = False


# Set for the duration of a request (REST) or a tool call (MCP); read by db.py for each connection.
current: ContextVar[Principal | None] = ContextVar("eax_principal", default=None)

_cache: dict[str, object] = {"at": 0.0, "map": {}}
_cache_lock = Lock()
CACHE_SECONDS = 30


def role_map(conn=None) -> dict[str, set[str]]:
    """Keycloak role -> global roles, from core.role_mappings (cached for 30 seconds)."""
    with _cache_lock:
        if time.monotonic() - float(_cache["at"]) < CACHE_SECONDS and _cache["map"]:
            return _cache["map"]  # type: ignore[return-value]
    from .db import get_engine  # late import: tests use this module without a database

    def load(c):
        out: dict[str, set[str]] = {}
        for k, a in c.execute(text("SELECT keycloak_role, app_role FROM core.role_mappings")):
            out.setdefault(k.lower(), set()).add(a)
        return out
    if conn is not None:
        mapping = load(conn)
    else:
        with get_engine().connect() as c:
            mapping = load(c)
    with _cache_lock:
        _cache.update(at=time.monotonic(), map=mapping)
    return mapping


def forget_role_map() -> None:
    with _cache_lock:
        _cache.update(at=0.0, map={})


def app_roles(keycloak_roles, mapping: dict[str, set[str]] | None = None) -> list[str]:
    """The global roles a set of Keycloak roles gives."""
    mapping = role_map() if mapping is None else mapping
    out: set[str] = set()
    for r in keycloak_roles or []:
        out |= {x for x in mapping.get(str(r).lower(), set()) if x in GLOBAL_ROLES}
    return sorted(out, key=APP_ROLES.index)


def allowed(roles, permission: str, model_roles=None) -> bool:
    """True when the global roles (or, for a model permission, the person's roles on that model) give it."""
    roles = set(roles or [])
    if SUPER_ADMIN in roles:
        return True
    if permission in GLOBAL_PERMISSIONS:
        return bool(roles & GLOBAL_PERMISSIONS[permission])
    if isinstance(model_roles, str):
        model_roles = [model_roles]
    return bool(set(model_roles or []) & MODEL_PERMISSIONS[permission])


def sees_every_model(roles) -> bool:
    return bool(set(roles or []) & SEES_EVERY_MODEL)


def model_roles(conn, username: str, model) -> list[str]:
    """A person's roles on a model (by guid); empty when none."""
    return [r for (r,) in conn.execute(text("""SELECT u.role FROM core.model_users u JOIN core.models m ON m.id = u.model_id
                                                WHERE m.guid = CAST(:m AS uuid) AND u.username = lower(:u)"""),
                                       {"m": str(model), "u": username})]


def is_model_admin_anywhere(conn, username: str) -> bool:
    """True when the person is Model Admin of at least one model (they may then look people up to give roles)."""
    return conn.execute(text("SELECT 1 FROM core.model_users WHERE username = lower(:u) AND role = 'model-admin' LIMIT 1"),
                        {"u": username}).first() is not None


def assigned_models(conn, username: str) -> list[dict]:
    """The models where a person has roles, with the roles and what they allow there."""
    by_model: dict[str, dict] = {}
    for r in conn.execute(text("""
        SELECT m.guid AS id, m.name, m.kind_code AS kind, u.role FROM core.model_users u
          JOIN core.models m ON m.id = u.model_id WHERE u.username = lower(:u) ORDER BY m.name, u.role"""),
            {"u": username}).mappings():
        m = by_model.setdefault(str(r["id"]), {"id": r["id"], "name": r["name"], "kind": r["kind"], "roles": []})
        m["roles"].append(r["role"])
    out = list(by_model.values())
    for m in out:
        m["roles"].sort(key=APP_ROLES.index)
        m["role"] = m["roles"][0]   # the highest, for screens that show one
        m["permissions"] = sorted(p for p, need in MODEL_PERMISSIONS.items() if set(m["roles"]) & need)
    return out


def describe(roles) -> dict[str, bool]:
    """Every global permission, and every model permission the global roles give on every model."""
    return {p: allowed(roles, p) for p in PERMISSIONS}
