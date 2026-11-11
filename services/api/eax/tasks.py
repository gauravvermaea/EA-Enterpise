"""Long work in the background (owner, 5 Nov 2026, D192; every slow button, D273).

A request that may take long on a large model (tagging, merging, importing, comparing, exporting, ...) is checked at
once (rights, name), then recorded in core.tasks and done by the job runner as the person who asked. The screen that
asked shows "working...", follows the task (GET /tasks/<id>) and shows the outcome; the person can leave the page: the
task drawer on the right shows every task with its progress, and when it ends a notification (category task) says so
on the Background tasks tab of Notifications, with the link back to the screen that asked and, for a file, the
download. A task's file is kept 24 hours (the minute job removes it then).

    create(conn, kind, model, user, label, params, link, inputs) -> task   queued, the job deferred by the caller
    run(task_id)                                                 the job: does the work, records done or failed
    progress(pct, note)                                          called by the work: how far it is (its own connection)
    get(conn, user, task) / mine(conn, user, active)             yours (a Super Admin sees every task)
    add_file / input_of / file_of / cleanup                      the files a task reads and makes
"""

from __future__ import annotations

import contextvars
import json
import logging
from typing import Any

from sqlalchemy import text

from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError

log = logging.getLogger(__name__)
FILE_HOURS = 24
_running: contextvars.ContextVar[int | None] = contextvars.ContextVar("eax_task", default=None)
# work on the projects' own database (when it is not the repository's) commits only after the repository's work did, so a
# project never points at models that were not kept (review, 7 Nov 2026)
_after: contextvars.ContextVar[list | None] = contextvars.ContextVar("eax_after_commit", default=None)


class commits_after:
    """Around the repository's transaction: the transactions handed to defer_commit commit once it has, or roll back."""

    def __enter__(self):
        self.todo: list = []
        self.token = _after.set(self.todo)
        return self

    def __exit__(self, kind, exc, tb):
        _after.reset(self.token)
        for tx, c in self.todo:
            try:
                if kind is None:
                    tx.commit()
                else:
                    tx.rollback()
            finally:
                c.close()
        return False


def defer_commit(tx, c) -> bool:
    """Hands a transaction to the commits_after around this work; False when there is none (it commits there and then)."""
    todo = _after.get()
    if todo is None:
        return False
    todo.append((tx, c))
    return True
KINDS = {"tag.create": "Tag a model", "sheet.build": "Build sheets", "load.preview": "Preview a load", "load.add": "Add a load",
         "delivery.accept": "Accept a delivery",
         "selftest.purge": "Purge self-test fixtures",
         "backup.infrastructure": "Infrastructure backup", "backup.application": "Application backup", "backup.model": "Back up a model",
         "backup.restore": "Restore a model backup", "backup.restore_all": "Restore every model of an application backup"}


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
            "link": t.get("link") or "", "progress": t.get("progress"), "progress_note": t.get("progress_note") or "",
            "file": t.get("file_name"), "done": t["status"] in ("done", "failed")}


SELECT = f"""SELECT t.*, m.guid AS model_guid,
                    (SELECT f.name FROM core.task_files f WHERE f.task_id = t.id AND f.role = 'result'
                        AND f.created_at > now() - interval '{FILE_HOURS} hours' ORDER BY f.id DESC LIMIT 1) AS file_name
               FROM core.tasks t LEFT JOIN core.models m ON m.id = t.model_id"""


def create(conn, kind: str, model: Any, user, label: str, params: dict, link: str = "",
           inputs: list[tuple[str, str, bytes]] | None = None) -> dict:
    """inputs: files that came with the request [(name, content type, bytes)], read by the work with input_of."""
    m = repo.get_model(conn, model) if model else None
    row = _one(conn, """INSERT INTO core.tasks (kind, model_id, label, params, requested_by, link)
                        VALUES (:k, :m, :l, CAST(:p AS jsonb), :u, :ln) RETURNING id""",
               k=kind, m=m["_id"] if m else None, l=label[:300], p=json.dumps(params, default=str), u=user.username.lower(),
               ln=link or "")
    for name, ctype, data in inputs or []:
        add_file(conn, row["id"], data, name, ctype, role="input")
    return _out(_one(conn, SELECT + " WHERE t.id = :i", i=row["id"]))


def add_file(conn, task_id: int, data: bytes, name: str, ctype: str, role: str = "result") -> None:
    conn.execute(text("""INSERT INTO core.task_files (task_id, name, content_type, content, role)
                         VALUES (:t, :n, :c, :b, :r)"""), {"t": task_id, "n": name, "c": ctype, "b": data, "r": role})


def input_of(conn, t: dict) -> tuple[bytes, str]:
    """The file uploaded with the request (bytes, its name)."""
    f = _one(conn, "SELECT name, content FROM core.task_files WHERE task_id = :t AND role = 'input' ORDER BY id LIMIT 1", t=t["id"])
    if not f:
        raise EditError("The uploaded file is no longer there; upload it again.", 404)
    return bytes(f["content"]), f["name"]


def progress(pct: int | None, note: str = "") -> None:
    """How far the running task is (0 to 100, None while unknown): written at once on a connection of its own, so the
    drawer shows it while the work's own transaction is still open. Does nothing outside a task."""
    tid = _running.get()
    if tid is None:
        return
    from .db import get_engine
    try:
        with get_engine().begin() as c:
            c.execute(text("UPDATE core.tasks SET progress = :p, progress_note = :n WHERE id = :i"),
                      {"p": None if pct is None else max(0, min(100, int(pct))), "n": (note or "")[:300], "i": tid})
    except Exception:  # noqa: BLE001 - progress is a courtesy; the work goes on
        log.debug("progress not recorded", exc_info=True)


def cleanup(conn) -> int:
    """The minute job: files of tasks older than FILE_HOURS go, and input files of finished tasks."""
    r = conn.execute(text(f"""DELETE FROM core.task_files f USING core.tasks t WHERE t.id = f.task_id
                               AND (f.created_at < now() - interval '{FILE_HOURS} hours'
                                    OR (f.role = 'input' AND t.status IN ('done', 'failed')))"""))
    return r.rowcount or 0


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


def mine(conn, user, active: bool = False, limit: int = 30, history: bool = False, offset: int = 0) -> dict:
    """active: running ones and those finished in the last 24 hours (the drawer); history: every finished one, newest
    first, a page at a time (the drawer's History, kept until the person deletes it); otherwise the latest ones."""
    if history:
        rows = _rows(conn, SELECT + """ WHERE t.requested_by = :u AND t.status IN ('done', 'failed')
                                       ORDER BY t.finished_at DESC NULLS LAST, t.id DESC LIMIT :n OFFSET :o""",
                     u=user.username.lower(), n=min(max(limit, 1), 200), o=max(offset, 0))
        total = _rows(conn, "SELECT count(*) AS n FROM core.tasks WHERE requested_by = :u AND status IN ('done', 'failed')",
                      u=user.username.lower())[0]["n"]
        return {"tasks": [_out(t) for t in rows], "total": total}
    rows = _rows(conn, SELECT + f""" WHERE t.requested_by = :u AND (NOT :a OR t.status IN ('queued', 'running')
                                          OR t.finished_at > now() - interval '{FILE_HOURS} hours')
                                   ORDER BY t.requested_at DESC LIMIT :n""", u=user.username.lower(), a=active, n=limit)
    return {"tasks": [_out(t) for t in rows]}


def delete_history(conn, user, ids: list | None = None) -> dict:
    """Deletes the person's own finished tasks: those given, or all of them. Running ones are never deleted; their files
    go with them (owner, 7 Nov 2026: the task history is kept until its owner deletes it)."""
    params = {"u": user.username.lower()}
    where = "requested_by = :u AND status IN ('done', 'failed')"
    if ids is not None:
        keep = [str(i) for i in ids if i]
        if not keep:
            raise EditError("Choose the tasks to delete.")
        where += " AND guid::text = ANY (CAST(:g AS text[]))"
        params["g"] = keep
    n = conn.execute(text(f"DELETE FROM core.tasks WHERE {where}"), params).rowcount or 0
    return {"deleted": n, "message": f"{n} finished task{'s' if n != 1 else ''} deleted from your history."}


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
    content, name, ctype = sh.build(conn, str(t["model_guid"]), p.get("types") or None, p.get("format") or "xlsx", user.username,
                                    bool(p.get("blank")))
    add_file(conn, t["id"], content, name, ctype)
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


def _delivery_accept(conn, t: dict, user) -> tuple[str, dict]:
    """Phase 34 (D465): a delivery becomes the person's changes, committed at once."""
    from . import deliveries
    p = t["params"] if isinstance(t["params"], dict) else json.loads(t["params"])
    out = deliveries.accept(conn, user, p["load"])
    return out["message"], {"load": p["load"], **{k: v for k, v in out.items() if k != "failed"}, "failed": out["failed"][:50]}


def _selftest_purge(conn, t: dict, user) -> tuple[str, dict]:
    """Phase 36.1 (D529): hard-deletes the self-test fixtures chosen, run by run (only what each run recorded)."""
    from .testing import fixtures as fx
    p = t["params"] if isinstance(t["params"], dict) else json.loads(t["params"])
    runs, picked = [int(r) for r in p.get("runs") or []], [int(i) for i in p.get("fixtures") or []]
    total = {"models": 0, "projects": 0, "service_accounts": 0, "credentials": 0, "history_versions": 0, "notes": []}
    for i, run in enumerate(runs):
        def say(pct, note, i=i):
            progress(int((i + pct / 100) * 100 / max(1, len(runs))), note)
        out = fx.purge(conn, run, user.username, fixture_ids=picked or None, progress=say)
        for k, v in out.items():
            total[k] = total[k] + v
    msg = (f"Purged {total['models']} model(s), {total['projects']} project(s), {total['service_accounts']} account(s) and "
           f"{total['credentials']} credential(s) of {len(runs)} self-test run(s); {total['history_versions']} history versions removed.")
    return msg, total


def _params(t: dict) -> dict:
    return t["params"] if isinstance(t["params"], dict) else json.loads(t["params"] or "{}")


def _backup_infrastructure(conn, t: dict, user) -> tuple[str, dict]:
    """D216: the operations helper makes the backup; this follows it until it is done (people keep working)."""
    import time

    from .api.admin import _ops_raw
    p = _params(t)
    _ops_raw("POST", "/backups/backup", {"tag": p.get("tag"), "by": user.username, "kind": p.get("kind") or "on-demand",
                                         "version": p.get("version") or "", "pinned": bool(p.get("pinned")),
                                         "keep": int(p.get("keep") or 0)}, timeout=30)
    started = time.time()
    while time.time() - started < 6 * 3600:
        time.sleep(3)
        st = _ops_raw("GET", "/backups", timeout=30).get("state") or {}
        if not st.get("busy"):
            res = st.get("result") or {}
            if res.get("status") == "stopped":
                return f"Infrastructure backup stopped: {res.get('error')}", {"name": res.get("name"), "stopped": True}
            if res.get("status") != "ok":
                raise EditError(f"The backup failed: {res.get('error') or st.get('error') or 'see the log on Administration > Backups'}")
            return (f"Infrastructure backup '{res.get('tag')}' made: {res.get('name')} "
                    f"({len((res.get('parts') or {}).get('databases') or [])} databases).", {"name": res.get("name")})
    raise EditError("The backup took more than six hours: see Administration > Backups.")


def _backup_application(conn, t: dict, user) -> tuple[str, dict]:
    from . import backups as bk
    p = _params(t)
    return bk.application_backup(conn, user, p.get("tag") or "application", p.get("models") or None)


def _backup_model(conn, t: dict, user) -> tuple[str, dict]:
    from . import backups as bk
    return bk.model_backup(conn, user, str(t["model_guid"]), _params(t).get("note") or "")


def _backup_restore_all(conn, t: dict, user) -> tuple[str, dict]:
    from . import backups as bk
    return bk.restore_application(conn, user, _params(t).get("name") or "")


def _backup_restore(conn, t: dict, user) -> tuple[str, dict]:
    from . import backups as bk
    return bk.restore(conn, user, _params(t))


WORK = {"tag.create": _tag_create, "sheet.build": _sheet_build, "load.preview": _load_preview, "load.add": _load_add,
        "delivery.accept": _delivery_accept, "selftest.purge": _selftest_purge,
        "backup.infrastructure": _backup_infrastructure, "backup.application": _backup_application,
        "backup.model": _backup_model, "backup.restore": _backup_restore, "backup.restore_all": _backup_restore_all}


def file_of(conn, user, task: Any) -> dict:
    t = get(conn, user, task)
    f = _one(conn, f"""SELECT f.name, f.content_type, f.content FROM core.task_files f JOIN core.tasks t ON t.id = f.task_id
                        WHERE t.guid = CAST(:g AS uuid) AND f.role = 'result'
                          AND f.created_at > now() - interval '{FILE_HOURS} hours' ORDER BY f.id DESC LIMIT 1""", g=t["id"])
    if not f:
        raise EditError("This task has no file: not made yet, or kept 24 hours and now removed (run it again).", 404)
    return f


def _error(exc: Exception) -> str:
    """The reason in words, as the screens say it."""
    from sqlalchemy.exc import DBAPIError

    from .metamodel_edit import _db_message
    if isinstance(exc, EditError):
        return str(exc)
    if isinstance(exc, DBAPIError):
        return _db_message(exc)
    if isinstance(exc, repo.NotFound):
        return str(exc)
    return f"{exc.__class__.__name__}: {exc}"


def _notify(conn, t: dict, actor: str, ok: bool, message: str) -> None:
    """D273: the person who asked hears that the task ended (the Background tasks tab of Notifications)."""
    from . import notify
    try:
        notify.create(conn, kind="task.done" if ok else "task.failed", category="task",
                      title=f"{'Done' if ok else 'Failed'}: {t['label']}", body=message or "", link=t.get("link") or "",
                      actor=actor, model_id=t.get("model_id"), recipients=[actor], include_actor=True, webhooks=False,
                      ref_kind="task", ref_id=t["id"])
    except Exception:  # noqa: BLE001 - the task's own outcome is recorded whatever happens here
        log.warning("task %s: notification not made", t["id"], exc_info=True)


def run(task_id: str, actor: str, roles: list[str]) -> None:
    """Does a task as the person who asked (the database checks their rights as in the screens)."""
    from . import audit, background  # noqa: F401 - background registers the kinds of D273 in WORK
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
        t["params"] = _params(t)
        mark = _running.set(t["id"])
        try:
            with commits_after(), get_engine().begin() as conn:
                message, result = WORK[t["kind"]](conn, t, user)
                result = dict(result or {})
                action = result.pop("_action", None) or t["kind"]
                details = {"name": t["params"].get("name"), "task": task_id, **(result.pop("_details", None) or {})}
                conn.execute(text("""UPDATE core.tasks SET status = 'done', message = :msg, result = CAST(:r AS jsonb),
                                            progress = 100, finished_at = now() WHERE id = :i"""),
                             {"msg": message, "r": json.dumps(result, default=str), "i": t["id"]})
                if action != "-":
                    audit.record(conn, actor=actor, action=action, object_type="model" if t["model_guid"] else "task",
                                 object_id=str(t["model_guid"] or task_id), details=details, source="job")
                _notify(conn, t, actor, True, message)
            log.info("task %s (%s) done: %s", task_id, t["kind"], message)
        except Exception as exc:  # recorded on the task so the screen can say why
            msg = _error(exc)
            with get_engine().begin() as conn:
                conn.execute(text("UPDATE core.tasks SET status = 'failed', message = :m, finished_at = now() WHERE id = :i"),
                             {"m": msg[:1000], "i": t["id"]})
                _notify(conn, t, actor, False, msg[:1000])
            log.exception("task %s (%s) failed", task_id, t["kind"])
        finally:
            _running.reset(mark)
    finally:
        perms.current.reset(token)
