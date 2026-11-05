"""Long work in the background (owner, 5 Nov 2026, D192).

A request that may take long on a large model (first: tagging a model, which reads every entity, value and
relationship) is checked at once (rights, name), then recorded in core.tasks and done by the job runner as the person
who asked. The screen that asked shows "working...", follows the task (GET /tasks/<id>) and says when it is done or
why it failed; the person can leave the page, the top bar tells them when it finishes.

    create(conn, kind, model, user, label, params) -> task       queued, the job deferred by the caller
    run(task_id)                                                 the job: does the work, records done or failed
    get(conn, user, task) / mine(conn, user, active)             yours (a Super Admin sees every task)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError

log = logging.getLogger(__name__)
KINDS = {"tag.create": "Tag a model", "sheet.build": "Build sheets", "load.preview": "Preview a load", "load.add": "Add a load"}


def _rows(conn, sql: str, **p) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), p).mappings().all()]


def _one(conn, sql: str, **p) -> dict | None:
    r = _rows(conn, sql, **p)
    return r[0] if r else None


def _out(t: dict) -> dict:
    res = t["result"] if isinstance(t["result"], dict) else json.loads(t["result"] or "{}")
    return {"id": str(t["guid"]), "kind": t["kind"], "label": t["label"], "status": t["status"], "message": t["message"],
            "result": res, "model_id": str(t["model_guid"]) if t.get("model_guid") else None, "requested_by": t["requested_by"],
            "requested_at": t["requested_at"], "started_at": t["started_at"], "finished_at": t["finished_at"],
            "done": t["status"] in ("done", "failed")}


SELECT = """SELECT t.*, m.guid AS model_guid FROM core.tasks t LEFT JOIN core.models m ON m.id = t.model_id"""


def create(conn, kind: str, model: Any, user, label: str, params: dict) -> dict:
    m = repo.get_model(conn, model) if model else None
    row = _one(conn, """INSERT INTO core.tasks (kind, model_id, label, params, requested_by)
                        VALUES (:k, :m, :l, CAST(:p AS jsonb), :u) RETURNING id""",
               k=kind, m=m["_id"] if m else None, l=label, p=json.dumps(params, default=str), u=user.username.lower())
    return _out(_one(conn, SELECT + " WHERE t.id = :i", i=row["id"]))


def set_job(conn, task_id: str, job_id: int) -> None:
    conn.execute(text("UPDATE core.tasks SET job_id = :j WHERE guid = CAST(:g AS uuid)"), {"j": job_id, "g": task_id})


def _visible(user) -> bool:
    return perms.SUPER_ADMIN in user.roles


def get(conn, user, task: Any) -> dict:
    g = repo._as_guid(task)
    t = _one(conn, SELECT + " WHERE t.guid = CAST(:g AS uuid)", g=str(g)) if g else None
    if not t or (t["requested_by"] != user.username.lower() and not _visible(user)):
        raise EditError("No such task.", 404)
    return _out(t)


def mine(conn, user, active: bool = False, limit: int = 30) -> dict:
    rows = _rows(conn, SELECT + """ WHERE t.requested_by = :u AND (NOT :a OR t.status IN ('queued', 'running')
                                          OR t.finished_at > now() - interval '10 minutes')
                                   ORDER BY t.requested_at DESC LIMIT :n""", u=user.username.lower(), a=active, n=limit)
    return {"tasks": [_out(t) for t in rows]}


# ---------------------------------------------------------------- the work (run by the job runner)
def _tag_create(conn, t: dict, user) -> tuple[str, dict]:
    from . import tags as tg
    p = t["params"] if isinstance(t["params"], dict) else json.loads(t["params"])
    out = tg.create_tag(conn, str(t["model_guid"]), user, p["name"], p.get("description", ""), bool(p.get("lock")))
    return (f"Tagged as '{out['name']}': {out['entities']} entities and {out['relationships']} relationships "
            f"at commit {out['commit']}.", out)


def _sheet_build(conn, t: dict, user) -> tuple[str, dict]:
    """The sheets for the chosen entity types, built now (D197), kept with the task until downloaded."""
    from . import sheets as sh
    p = t["params"] if isinstance(t["params"], dict) else json.loads(t["params"])
    content, name, ctype = sh.build(conn, str(t["model_guid"]), p.get("types") or None, p.get("format") or "xlsx", user.username)
    conn.execute(text("INSERT INTO core.task_files (task_id, name, content_type, content) VALUES (:t, :n, :c, :b)"),
                 {"t": t["id"], "n": name, "c": ctype, "b": content})
    return f"{name} is ready ({len(content) // 1024 + 1} KB).", {"file": name, "bytes": len(content)}


def _load_preview(conn, t: dict, user) -> tuple[str, dict]:
    from . import loads
    p = t["params"] if isinstance(t["params"], dict) else json.loads(t["params"])
    out = loads.preview(conn, p["load"], user)
    if out["status"] == "mapping":
        return "Some sheets need their columns mapped before the preview.", {"load": p["load"], **out}
    return f"Preview of {p.get('file', 'the load')}: {out['message']}", {"load": p["load"], **out}


def _load_add(conn, t: dict, user) -> tuple[str, dict]:
    from . import loads
    p = t["params"] if isinstance(t["params"], dict) else json.loads(t["params"])
    out = loads.add(conn, user, p["load"])
    return out["message"], {"load": p["load"], **{k: v for k, v in out.items() if k != "failed"}, "failed": out["failed"][:50]}


WORK = {"tag.create": _tag_create, "sheet.build": _sheet_build, "load.preview": _load_preview, "load.add": _load_add}


def file_of(conn, user, task: Any) -> dict:
    t = get(conn, user, task)
    f = _one(conn, """SELECT f.name, f.content_type, f.content FROM core.task_files f JOIN core.tasks t ON t.id = f.task_id
                       WHERE t.guid = CAST(:g AS uuid) ORDER BY f.id DESC LIMIT 1""", g=t["id"])
    if not f:
        raise EditError("This task has no file (yet).", 404)
    return f


def run(task_id: str, actor: str, roles: list[str]) -> None:
    """Does a task as the person who asked (the database checks their rights as in the screens)."""
    from . import audit
    from . import settings as app_settings
    from .db import get_engine
    app_settings.apply_log_level()
    user = perms.Principal(actor, tuple(roles or ()))
    token = perms.current.set(user)
    try:
        with get_engine().begin() as conn:
            t = _one(conn, SELECT + " WHERE t.guid = CAST(:g AS uuid)", g=task_id)
            if not t or t["status"] != "queued":
                return
            conn.execute(text("UPDATE core.tasks SET status = 'running', started_at = now() WHERE id = :i"), {"i": t["id"]})
        try:
            with get_engine().begin() as conn:
                message, result = WORK[t["kind"]](conn, t, user)
                conn.execute(text("""UPDATE core.tasks SET status = 'done', message = :msg, result = CAST(:r AS jsonb),
                                            finished_at = now() WHERE id = :i"""),
                             {"msg": message, "r": json.dumps(result, default=str), "i": t["id"]})
                audit.record(conn, actor=actor, action=t["kind"], object_type="model" if t["model_guid"] else "task",
                             object_id=str(t["model_guid"] or task_id), details={"name": (t["params"] or {}).get("name"),
                                                                                  "task": task_id}, source="job")
            log.info("task %s (%s) done: %s", task_id, t["kind"], message)
        except Exception as exc:  # recorded on the task so the screen can say why
            msg = str(exc) if isinstance(exc, EditError) else f"{exc.__class__.__name__}: {exc}"
            with get_engine().begin() as conn:
                conn.execute(text("UPDATE core.tasks SET status = 'failed', message = :m, finished_at = now() WHERE id = :i"),
                             {"m": msg[:1000], "i": t["id"]})
            log.exception("task %s (%s) failed", task_id, t["kind"])
    finally:
        perms.current.reset(token)
