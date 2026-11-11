"""A project's tasks (owner, 8 Nov 2026, D298): a scratchpad of what people are doing, not project management.

- A task has a title, notes (rich text), a status and, if wanted, the person it is assigned to and the step or sub step
  it belongs to. No dates and no deadlines.
- Statuses: the standard ones (STANDARD) and the project's own, which anyone who contributes adds in the Tasks tab.
- Everyone on the project sees every task. Contributors add and change tasks and may assign them to anyone on the
  project; the person a task is assigned to may change its status and notes even without a contributing role.
  The person who made a task, a Project Admin or a Lead Architect deletes it.
- Finishing a task never finishes its step: someone marks the step done (as with sub steps, D295).
- Assigning a task to someone else tells them (a notification, category request).
(Not eax/tasks.py: that is the background work of slow buttons, D192.)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from . import notify
from . import projects as pj
from .metamodel_edit import EditError
from .project_work import clean_html

_rows, _one = pj._rows, pj._one

STANDARD = ("Created", "Open", "To do", "Done", "Not done", "Rejected")
FINISHED = ("Done", "Not done", "Rejected")
READ_ONLY = ("finishing", "frozen", "merged", "closed")


def statuses(conn, p: dict) -> list[str]:
    own = [r["name"] for r in _rows(conn, "SELECT name FROM proj.task_statuses WHERE project_id = :p ORDER BY sort_order, name", p=p["id"])]
    return [*STANDARD, *[s for s in own if s not in STANDARD]]


def _members(conn, p: dict) -> set[str]:
    return {r["u"] for r in _rows(conn, "SELECT DISTINCT lower(username) AS u FROM proj.members WHERE project_id = :p", p=p["id"])}


def _step(conn, p: dict, step: Any) -> int | None:
    if step in (None, "", 0, "0"):
        return None
    try:
        sid = int(step)
    except (TypeError, ValueError) as exc:
        raise EditError("The step is given by its number.") from exc
    if not _one(conn, "SELECT id FROM proj.steps WHERE id = :s AND project_id = :p", s=sid, p=p["id"]):
        raise EditError("No such step in this project.", 404)
    return sid


def _may(conn, p: dict, user, what: str) -> bool:
    try:
        pj._need(conn, p, user, what)
        return True
    except EditError:
        return False


_SELECT = """SELECT t.*, s.name AS step_name, s.phase AS step_phase, s.done_at IS NOT NULL AS step_done, ps.name AS parent_name
               FROM proj.tasks t
               LEFT JOIN proj.steps s ON s.id = t.step_id
               LEFT JOIN proj.steps ps ON ps.id = s.parent_step_id"""


def _out(r: dict) -> dict:
    return {"id": str(r["guid"]), "title": r["title"], "notes_html": r["notes_html"], "status": r["status"],
            "finished": r["status"] in FINISHED, "assigned_to": r["assigned_to"], "created_by": r["created_by"],
            "created_at": r["created_at"], "modified_by": r["modified_by"] or r["created_by"],
            "modified_at": r["modified_at"] or r["created_at"],
            "step": ({"id": r["step_id"], "name": r["step_name"], "phase": r["step_phase"], "parent": r["parent_name"] or "",
                      "done": bool(r["step_done"])} if r["step_id"] else None)}


def listing(conn, project: Any, user) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    rows = _rows(conn, _SELECT + " WHERE t.project_id = :p ORDER BY t.created_at DESC, t.id DESC", p=p["id"])
    steps = _rows(conn, """SELECT s.id, s.phase, s.name, ps.name AS parent_name
                             FROM proj.steps s LEFT JOIN proj.steps ps ON ps.id = s.parent_step_id
                            WHERE s.project_id = :p AND NOT s.removed
                            ORDER BY s.phase, coalesce(ps.seq, s.seq), s.parent_step_id NULLS FIRST, s.seq""", p=p["id"])
    from . import iterations as it
    cur = it.current(conn, p)
    tasks = [_out(r) for r in rows]
    for t in tasks:      # a task on a step of a frozen phase is paused, not deleted (D572)
        t["paused"] = bool(t["step"]) and not it.enabled(cur, t["step"]["phase"])
    return {"tasks": tasks, "statuses": statuses(conn, p), "iteration": cur, "standard": list(STANDARD),
            "finished": list(FINISHED), "people": sorted(_members(conn, p)), "me": user.username.lower(),
            "steps": [{"id": s["id"], "phase": s["phase"], "name": s["name"], "parent": s["parent_name"] or ""} for s in steps],
            "may_add": _may(conn, p, user, "contribute"), "may_admin": _may(conn, p, user, "admin")}


def _row(conn, p: dict, tid: str) -> dict:
    r = _one(conn, _SELECT + " WHERE t.project_id = :p AND t.guid = CAST(:g AS uuid)", p=p["id"], g=tid)
    if not r:
        raise EditError("No such task in this project.", 404)
    return r


def _clean(conn, p: dict, d: dict, base: dict | None = None) -> dict:
    v = {**(base or {}), **d}
    title = (v.get("title") or "").strip()
    if not title:
        raise EditError("Give the task a title.")
    status = (v.get("status") or "Created").strip()
    known = statuses(conn, p)
    if status not in known:
        raise EditError(f"The status is one of: {', '.join(known)}.")
    who = (v.get("assigned_to") or "").strip().lower()
    if who and who not in _members(conn, p):
        raise EditError(f"{who} is not on this project: a task is assigned to someone on the project.")
    return {"title": title[:300], "notes_html": clean_html(v.get("notes_html")), "status": status, "assigned_to": who,
            "step_id": _step(conn, p, v.get("step_id"))}


def _tell(conn, p: dict, user, title: str, who: str) -> None:
    if who and who != user.username.lower():
        notify.create(pj.core(conn), kind="project.task_assigned", category="request", actor=user.username,
                      title=f"Task for you: {title}", body=f"Project {p['name']}: {user.username} assigned you a task.",
                      link=f"#/projects/{p['guid']}/tasks", recipients=[who])


def add(conn, project: Any, user, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    v = _clean(conn, p, d)
    g = conn.execute(text("""INSERT INTO proj.tasks (project_id, step_id, title, notes_html, status, assigned_to, created_by)
                             VALUES (:p, :step_id, :title, :notes_html, :status, :assigned_to, :u) RETURNING guid::text"""),
                     {**v, "p": p["id"], "u": user.username}).scalar()
    _tell(conn, p, user, v["title"], v["assigned_to"])
    return {"id": g, "message": f"Task added: {v['title']}" + (f" (assigned to {v['assigned_to']})" if v["assigned_to"] else "")}


def update(conn, project: Any, user, tid: str, d: dict) -> dict:
    """Contributors change anything; the person it is assigned to changes its status and notes."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    r = _row(conn, p, tid)
    if not _may(conn, p, user, "contribute"):
        if p.get("status") in READ_ONLY:
            raise EditError(f"{p['name']} is {p['status']}: it is read only.", 409)
        if r["assigned_to"] != user.username.lower() or set(d) - {"status", "notes_html"}:
            raise EditError("Only someone who contributes to the project, or the person the task is assigned to "
                            "(its status and notes), changes a task.", 403)
    base = {k: r[k] for k in ("title", "notes_html", "status", "assigned_to", "step_id")}
    v = _clean(conn, p, d, base)
    conn.execute(text("""UPDATE proj.tasks SET title = :title, notes_html = :notes_html, status = :status, assigned_to = :assigned_to,
                                step_id = :step_id, modified_by = :u, modified_at = now() WHERE id = :i"""),
                 {**v, "u": user.username, "i": r["id"]})
    if v["assigned_to"] != r["assigned_to"]:
        _tell(conn, p, user, v["title"], v["assigned_to"])
    msg = f"Saved: {v['title']}"
    if v["status"] != r["status"]:
        msg = f"{v['title']}: {v['status']}"
        if v["status"] in FINISHED and v["step_id"]:
            msg += " (the step stays as it is: mark the step done on its own)"
    return {"id": tid, "message": msg}


def delete(conn, project: Any, user, tid: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    r = _row(conn, p, tid)
    if r["created_by"].lower() != user.username.lower() and not _may(conn, p, user, "admin"):
        raise EditError("The person who made the task, a Project Admin or a Lead Architect deletes it.", 403)
    conn.execute(text("DELETE FROM proj.tasks WHERE id = :i"), {"i": r["id"]})
    return {"message": f"Task deleted: {r['title']}"}


def add_status(conn, project: Any, user, name: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    name = " ".join((name or "").split())[:40]
    if not name:
        raise EditError("Give the status a name.")
    if name.lower() in {s.lower() for s in statuses(conn, p)}:
        raise EditError(f"{name} is a status already.")
    n = conn.execute(text("SELECT coalesce(max(sort_order), 0) + 1 FROM proj.task_statuses WHERE project_id = :p"), {"p": p["id"]}).scalar()
    conn.execute(text("INSERT INTO proj.task_statuses (project_id, name, sort_order, added_by) VALUES (:p, :n, :o, :u)"),
                 {"p": p["id"], "n": name, "o": n, "u": user.username})
    return {"message": f"Status added: {name}", "statuses": statuses(conn, p)}


def delete_status(conn, project: Any, user, name: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    if name in STANDARD:
        raise EditError(f"{name} is a standard status: it stays.")
    used = (_one(conn, "SELECT count(*) AS n FROM proj.tasks WHERE project_id = :p AND status = :s", p=p["id"], s=name) or {"n": 0})["n"]
    if used:
        raise EditError(f"{used} task(s) have the status {name}: change them first.", 409)
    conn.execute(text("DELETE FROM proj.task_statuses WHERE project_id = :p AND name = :s"), {"p": p["id"], "s": name})
    return {"message": f"Status removed: {name}", "statuses": statuses(conn, p)}
