"""Who may do what (build phase 3.1, D58, D59, D60, D89, D90, D92, D96).

Two kinds of role:
  * Global roles, given in Keycloak: Super Admin, IT Admin, User Admin, Keycloak Admin, Model Creator,
    Library Admin (curates the model library, D118), and User (everyone who may sign in). Keycloak roles map to them in core.role_mappings
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
MODEL_CREATOR, LIBRARY_ADMIN, USER = "model-creator", "library-admin", "user"
GLOBAL_ROLES = [SUPER_ADMIN, IT_ADMIN, USER_ADMIN, KEYCLOAK_ADMIN, MODEL_CREATOR, LIBRARY_ADMIN, USER]
# model roles (per model, several allowed on one model)
MODEL_ADMIN, MODEL_SUB_ADMIN, ARCHITECT, REPORT_VIEWER = "model-admin", "model-sub-admin", "architect", "report-viewer"
COMMITTER, HISTORY_VIEWER = "committer", "history-viewer"   # phase 8 (D165, D151)
MODEL_ROLES = [MODEL_ADMIN, MODEL_SUB_ADMIN, COMMITTER, ARCHITECT, HISTORY_VIEWER, REPORT_VIEWER]   # highest first
APP_ROLES = GLOBAL_ROLES + MODEL_ROLES

# Global permissions: any one of these global roles (Super Admin always)
GLOBAL_PERMISSIONS: dict[str, set[str]] = {
    "system.operate": {IT_ADMIN},          # jobs, audit log, SQL window, backups
    "users.read": {USER_ADMIN},            # the Users page: people, roles, which models (Model Admins: see access.py)
    "roles.map": {USER_ADMIN},             # map Keycloak roles to global roles
    "keycloak.console": {KEYCLOAK_ADMIN},
    "models.all": set(),                   # read every model: Super Admin only
    "models.create": {MODEL_CREATOR},      # create a model and become its Model Admin (phase 4)
    "models.delete": set(),                # delete a model: Super Admin only (D121)
    "library.curate": {LIBRARY_ADMIN},     # create, publish, promote, upload and withdraw library models (D118)
    "settings.manage": set(),              # change settings and restart the system: Super Admin only (phase 10, D183)
    "projects.create": {USER, MODEL_CREATOR, LIBRARY_ADMIN},   # set up an architecture project (phase 13, D259)
    "projects.library": set(),             # the project library: Super Admin only (phase 13, D258)
    "surveys.create": {MODEL_CREATOR, LIBRARY_ADMIN},   # make and run surveys (phase 38.1, D447)
    "maturity.manage": set(),              # EA capability maturity assessments: Super Admin only (phase 40, D451)
}
# Model permissions: the person's roles on that model
MODEL_PERMISSIONS: dict[str, set[str]] = {
    "model.read": {MODEL_ADMIN, ARCHITECT, MODEL_SUB_ADMIN, REPORT_VIEWER, COMMITTER, HISTORY_VIEWER},
    "model.content": {MODEL_ADMIN, ARCHITECT, MODEL_SUB_ADMIN, COMMITTER},   # D90: Model Admins too
    "model.commit": {MODEL_ADMIN, MODEL_SUB_ADMIN, COMMITTER},     # D165: commit, reject, send back, roll back
    "model.history": {MODEL_ADMIN, HISTORY_VIEWER},                # D151: everyone's commits, not only your own
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
    ("user_library_admin", "eax-library-admin", {}),
    ("user_model_creator", "eax-model-creator", {"Karoo Re (independent)": [MODEL_ADMIN], "Lean EA metamodel": [MODEL_ADMIN],
                                                 "Karoo Digital (lean)": [MODEL_ADMIN]}),
    ("user_model_admin", "eax-user", {"Fynbos Mutual (group)": [MODEL_ADMIN], "Fynbos Life": [MODEL_ADMIN],
                                      "Sample insurance model": [ARCHITECT], "Protea Insurance (demo estate)": [MODEL_ADMIN]}),
    ("user_architect", "eax-user", {"Sample insurance model": [ARCHITECT], "Fynbos Life": [ARCHITECT],
                                    "Fynbos Commercial": [MODEL_SUB_ADMIN, REPORT_VIEWER],
                                    "Protea Insurance (demo estate)": [ARCHITECT]}),
    ("user_model_sub_admin", "eax-user", {"Sample insurance model": [MODEL_SUB_ADMIN], "Fynbos Life": [MODEL_SUB_ADMIN],
                                          "Fynbos Commercial": [MODEL_SUB_ADMIN], "Karoo Re (independent)": [MODEL_SUB_ADMIN]}),
    ("user_committer", "eax-user", {"Protea Insurance (demo estate)": [COMMITTER], "Sample insurance model": [COMMITTER]}),
    ("user_history_viewer", "eax-user", {"Protea Insurance (demo estate)": [HISTORY_VIEWER, REPORT_VIEWER]}),
    ("user_report_viewer", "eax-user", {"Fynbos Mutual (group)": [REPORT_VIEWER], "Sample insurance model": [REPORT_VIEWER],
                                        "Protea Insurance (demo estate)": [REPORT_VIEWER]}),
    ("user_global_architect", "eax-user", {"*": [ARCHITECT]}),
    # phase 13 (D259): project roles are given on a project, not in Keycloak; the sample project gives them these
    ("user_project_admin", "eax-user", {}),
    ("user_lead_architect", "eax-user", {}),
    ("user_stakeholder", "eax-user", {}),
]
# Laptop only (phase 13): the people of the sample architecture project and their project roles
PROJECT_TEST_ROLES = [("user_project_admin", "project-admin"), ("user_lead_architect", "lead-architect"),
                      ("user_architect", "architect"), ("user_model_admin", "model-admin"),
                      ("user_model_sub_admin", "model-sub-admin"), ("user_stakeholder", "stakeholder")]


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


GROUP_PREFIX = "group:"


def group_keys(groups) -> list[str]:
    """The mapping keys of a token's "groups" claim (phase 36, D503): each group as "group:<name>", matched without
    regard to case. A full path ("/EA/Architects") also gives its last part ("group:architects"), so a mapping works
    whether Keycloak sends paths or names; Entra ID object IDs are kept as they come."""
    out: list[str] = []
    for g in groups or []:
        g = str(g).strip()
        if not g:
            continue
        out.append(GROUP_PREFIX + g.lower())
        if "/" in g:
            last = g.rstrip("/").rsplit("/", 1)[-1]
            if last:
                out.append(GROUP_PREFIX + last.lower())
    return sorted(set(out))


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
    return [r["role"] for r in conn.execute(text("""SELECT u.role FROM core.model_users u JOIN core.models m ON m.id = u.model_id
                                                WHERE m.guid = CAST(:m AS uuid) AND u.username = lower(:u)"""),
                                       {"m": str(model), "u": username}).mappings().all()]


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
