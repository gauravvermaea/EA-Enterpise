"""The first-run setup of a new installation (UI-009, phase 16.3, D339).

The first Super Admin is walked once through the essentials, each step a link to the screen where it is done: the
application settings, the people and their roles, the parts in use, the template libraries, the organisation's charter
and principles, and when backups run. A step is done when the installation shows it (settings changed, the charter
approved) or when the Super Admin marks it done; the whole is put away with "finished" (it can be opened again from
System admin > Wizards). Kept in core.settings under the key first_run (not a setting of the console).
"""

from __future__ import annotations

import json

from sqlalchemy import text

from . import permissions as perms
from .metamodel_edit import EditError

KEY = "first_run"
STEPS = [
    ("settings", "Application settings", "The currency, the time zone, the date and number formats everyone sees.", "#/admin/application"),
    ("people", "People and their roles", "Who signs in and with which global role (given in Keycloak); the first architects and admins.",
     "#/admin/users"),
    ("parts", "The parts in use", "Projects, Repository and References, and the optional services (reports, documents, draw.io, MCP).",
     "#/admin/system"),
    ("templates", "Template libraries for projects", "EA Explorer's own is ready; add TOGAF 10 (your licensed copy) or your own.",
     "#/project-admin/library"),
    ("charter", "The organisation's architecture charter", "Filled in from the seed: read it, change it, approve it.", ""),
    ("principles", "The organisation's principles", "Areas, the principles, and which are enforced in every project.", "#/project-admin/principles"),
    ("backups", "When backups run", "The infrastructure and application backups, and how many are kept.", "#/admin/backups"),
]


def _state(conn) -> dict:
    r = conn.execute(text("SELECT value FROM core.settings WHERE key = :k"), {"k": KEY}).scalar()
    if isinstance(r, str):
        try:
            r = json.loads(r)
        except ValueError:
            r = None
    return r if isinstance(r, dict) else {"done": False, "marked": {}}


def _save(conn, state: dict) -> None:
    conn.execute(text("""INSERT INTO core.settings (key, value, name) VALUES (:k, CAST(:v AS jsonb), 'First-run setup')
                         ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, modified_at = now(),
                             modified_by = core.current_actor(), row_version = core.settings.row_version + 1"""),
                 {"k": KEY, "v": json.dumps(state)})


def _seen(conn) -> dict[str, bool]:
    """What the installation shows is done already."""
    seen: dict[str, bool] = {}
    from . import settings as st
    try:
        app = [s for s in st.describe(conn)["application"] if s.get("modified_by")]
        seen["settings"] = bool(app)
    except Exception:  # noqa: BLE001 - only a hint
        pass
    try:
        from . import org_repository as orgr
        from . import projects as pj
        with pj.connections(False) as pc:
            seen["templates"] = bool(pj._one(pc, "SELECT 1 AS x FROM proj.template_setup WHERE id = 1"))
            ch = pj._one(pc, """SELECT c.state FROM proj.charters c JOIN proj.projects p ON p.id = c.project_id WHERE p.base_kind = 'org'""")
            seen["charter"] = bool(ch and ch["state"] == "Approved")
            seen["_org"] = orgr.org_base(pc)
    except Exception:  # noqa: BLE001 - projects may be switched off or not set up
        pass
    return seen


def status(conn, user) -> dict:
    st_ = _state(conn)
    seen = _seen(conn)
    org = seen.pop("_org", None)
    steps = []
    for key, label, why, link in STEPS:
        if key == "charter":
            link = f"#/projects/{org['id']}/charter" if org else "#/repository"
        done = bool(st_.get("marked", {}).get(key)) or bool(seen.get(key))
        steps.append({"key": key, "label": label, "why": why, "link": link, "done": done,
                      "seen": bool(seen.get(key)), "marked": bool(st_.get("marked", {}).get(key))})
    return {"finished": bool(st_.get("done")), "steps": steps, "done": sum(1 for s in steps if s["done"]), "total": len(steps),
            "show": perms.SUPER_ADMIN in (user.roles or []) and not st_.get("done")}


def mark(conn, user, d: dict) -> dict:
    """{step, done} marks one step; {finished: true|false} puts the setup away (or opens it again). Super Admins."""
    if perms.SUPER_ADMIN not in (user.roles or []):
        raise EditError("The first-run setup is for Super Admins.", 403)
    st_ = _state(conn)
    if "finished" in d:
        st_["done"] = bool(d["finished"])
    if d.get("step"):
        if d["step"] not in {k for k, *_ in STEPS}:
            raise EditError("No such step.", 404)
        st_.setdefault("marked", {})[d["step"]] = bool(d.get("done", True))
    _save(conn, st_)
    return status(conn, user)
