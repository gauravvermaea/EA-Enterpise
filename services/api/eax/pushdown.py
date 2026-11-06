"""Metamodel versions pushed down the model hierarchy (phase 8.1, D84, D209).

A model's Model Admin pushes the metamodel versions published since its last push (made in the metamodel editor or
the grids) to the models directly under it, as one package: forced (made in each child at once) or offered (each
child's Model Admin accepts or rejects the whole package). A package made in a child becomes the child's own new
metamodel version, which its Model Admin may push on to the level below in the same way. A rejected package leaves the
child diverged from its parent, kept in its lineage (core.metamodel_push_targets).

Replaying a change on a child: the change names items by guid; a child's copy of an item has origin_guid = the
parent's guid (set when the model was created from it, and here for items a package makes), so each guid is
translated to the child's own item. What cannot be found makes the package fail for that child, saying why.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import change_docs, notify
from . import metamodel_edit as ed
from . import repository as repo
from .notify import _one, _rows

TABLES = ("entity_types", "relationship_types", "attribute_types", "item_attributes", "layers", "pick_lists",
          "pick_list_values", "validation_rules", "allowed_relationships")


class PushError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _as_uuid(v) -> str | None:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, str) and len(v) == 36:
        try:
            return str(uuid.UUID(v))
        except ValueError:
            return None
    return None


def _where(conn, guid: str, model_id: int) -> tuple[str, dict] | None:
    """The metamodel table and row of a guid in a model."""
    for t in TABLES:
        r = _one(conn, f"SELECT id, guid, origin_guid FROM core.{t} WHERE guid = CAST(:g AS uuid) AND model_id = :m",
                 g=guid, m=model_id)
        if r:
            return t, r
    return None


def _translate(conn, value: Any, parent_id: int, child_id: int) -> Any:
    """The same change in the child's terms: every guid of a parent's item becomes the child's copy of it."""
    if isinstance(value, dict):
        return {k: _translate(conn, v, parent_id, child_id) for k, v in value.items()}
    if isinstance(value, list):
        return [_translate(conn, v, parent_id, child_id) for v in value]
    g = _as_uuid(value)
    if not g:
        return value
    found = _where(conn, g, parent_id)
    if not found:
        return value        # not a metamodel item of the parent (an entity, a model): left as it is
    table, _row = found
    mine = _one(conn, f"SELECT guid FROM core.{table} WHERE model_id = :m AND origin_guid = CAST(:g AS uuid)", m=child_id, g=g)
    if not mine:
        name = _one(conn, f"SELECT * FROM core.{table} WHERE guid = CAST(:g AS uuid)", g=g) or {}
        label = name.get("name") or name.get("code") or name.get("value") or g
        raise PushError(f"This model has no copy of {table.replace('_', ' ')[:-1]} '{label}' (it was removed or made here "
                        "on its own), so the change to it cannot be made.", 409)
    return str(mine["guid"])


def _link_made(conn, parent_res: Any, child_res: Any, child_id: int) -> None:
    """Items the change made in the child are marked as copies of the parent's (origin_guid), so later packages find them."""
    if isinstance(parent_res, dict) and isinstance(child_res, dict):
        for k in parent_res:
            if k in child_res:
                _link_made(conn, parent_res[k], child_res[k], child_id)
        return
    if isinstance(parent_res, list) and isinstance(child_res, list):
        for a, b in zip(parent_res, child_res, strict=False):
            _link_made(conn, a, b, child_id)
        return
    pg, cg = _as_uuid(parent_res), _as_uuid(child_res)
    if not pg or not cg or pg == cg:
        return
    found = _where(conn, cg, child_id)
    if found and found[1]["origin_guid"] is None:
        conn.execute(text(f"UPDATE core.{found[0]} SET origin_guid = CAST(:p AS uuid) WHERE id = :i"), {"p": pg, "i": found[1]["id"]})


# ---------------------------------------------------------------- what can be pushed

def _model(conn, model) -> dict:
    return repo.get_model(conn, model)


def _bypass(conn, on: bool) -> None:
    """Every model below is pushed to, whether or not the person pushing has a role there (D84): the model rows are
    read past row-level security for that moment only (it counts only for the API's own login)."""
    conn.execute(text("SELECT set_config('eax.rls_bypass', :v, true)"), {"v": "on" if on else ""})


def children(conn, model_id: int) -> list[dict]:
    _bypass(conn, True)
    try:
        return _rows(conn, """SELECT id, guid, name, kind_code, is_locked, lifecycle = 'archived' AS is_archived FROM core.models
                               WHERE parent_model_id = :m ORDER BY name""", m=model_id)
    finally:
        _bypass(conn, False)


def unpushed(conn, model_id: int) -> list[dict]:
    """The model's metamodel versions not yet pushed down (newest last), each with its changes; versions made another
    way (a draft applied, a package) have no recorded changes and are listed as not pushable."""
    vers = _rows(conn, """
        SELECT v.version, v.note, v.changed_by, v.changed_at,
               (SELECT count(*) FROM core.metamodel_version_changes c WHERE c.model_id = v.model_id AND c.version = v.version) AS changes
          FROM core.metamodel_versions v
         WHERE v.model_id = :m AND v.version > coalesce((SELECT max(version) FROM core.metamodel_versions_pushed p
                                                          WHERE p.model_id = :m), 0)
           AND v.version > 1
         ORDER BY v.version""", m=model_id)
    for v in vers:
        v["pushable"] = v["changes"] > 0
    return vers


def overview(conn, model) -> dict:
    """The push-down page of a model: what it can push, to whom, what was pushed, and what arrived from above."""
    m = _model(conn, model)
    mid = m["_id"]
    kids = children(conn, mid)
    parent = _one(conn, """SELECT p.guid, p.name FROM core.models c JOIN core.models p ON p.id = c.parent_model_id
                            WHERE c.id = :m""", m=mid)
    _bypass(conn, True)   # the models below by name, even those the person has no role on
    out_pushes = _rows(conn, """
        SELECT p.id, p.guid AS id_guid, p.versions, p.mode, p.fill_defaults, p.note, p.pushed_by, p.pushed_at,
               coalesce(json_agg(json_build_object('model', cm.name, 'model_id', cm.guid, 'status', t.status,
                         'decided_by', t.decided_by, 'decided_at', t.decided_at, 'note', t.note, 'error', t.error)
                         ORDER BY cm.name) FILTER (WHERE t.id IS NOT NULL), '[]') AS targets
          FROM core.metamodel_pushes p LEFT JOIN core.metamodel_push_targets t ON t.push_id = p.id
          LEFT JOIN core.models cm ON cm.id = t.model_id
         WHERE p.from_model_id = :m GROUP BY p.id ORDER BY p.id DESC LIMIT 50""", m=mid)
    _bypass(conn, False)
    incoming = _rows(conn, """
        SELECT t.id, p.guid AS push_id, pm.name AS from_model, pm.guid AS from_model_id, p.versions, p.mode, p.note,
               p.pushed_by, p.pushed_at, t.status, t.decided_by, t.decided_at, t.note AS decision_note, t.error,
               t.applied_version,
               (SELECT json_agg(json_build_object('op', c.op, 'note', c.note) ORDER BY c.version, c.seq)
                  FROM core.metamodel_version_changes c WHERE c.model_id = p.from_model_id AND c.version = ANY (p.versions)) AS changes
          FROM core.metamodel_push_targets t JOIN core.metamodel_pushes p ON p.id = t.push_id
          JOIN core.models pm ON pm.id = p.from_model_id
         WHERE t.model_id = :m ORDER BY t.id DESC LIMIT 50""", m=mid)
    for x in out_pushes:
        x["targets"] = x["targets"] if isinstance(x["targets"], list) else json.loads(x["targets"])
        x["id"] = str(x.pop("id_guid"))
    for x in incoming:
        x["changes"] = x["changes"] if isinstance(x["changes"], list) else json.loads(x["changes"] or "[]")
    pend = unpushed(conn, mid)
    return {"model": {"id": str(m["id"]), "name": m["name"], "metamodel_version": m.get("metamodel_version")},
            "parent": {"id": str(parent["guid"]), "name": parent["name"]} if parent else None,
            "children": [{"id": str(k["guid"]), "name": k["name"], "kind": k["kind_code"],
                          "read_only": bool(k["is_locked"] or k["is_archived"] or k["kind_code"] not in ("project", "template"))}
                         for k in kids],
            "unpushed": pend, "pushable": [v["version"] for v in pend if v["pushable"]],
            "pushes": out_pushes, "incoming": incoming,
            "diverged": [x for x in incoming if x["status"] == "rejected"]}


# ---------------------------------------------------------------- pushing and deciding

def push(conn, model, actor: str, mode: str, fill_defaults: bool = True, note: str = "", came_from: int | None = None) -> dict:
    if mode not in ("forced", "offered"):
        raise PushError("Push forced (made at once) or offered (each model below accepts or rejects it).")
    m = _model(conn, model)
    mid = m["_id"]
    pend = unpushed(conn, mid)
    versions = [v["version"] for v in pend if v["pushable"]]
    if not versions:
        raise PushError("Nothing to push: no metamodel version made in the editor or the grids since the last push.", 409)
    kids = children(conn, mid)
    if not kids:
        raise PushError(f"{m['name']} has no models under it.", 409)
    push_id = conn.execute(text("""
        INSERT INTO core.metamodel_pushes (from_model_id, versions, mode, fill_defaults, note, came_from, pushed_by)
        VALUES (:m, CAST(:v AS integer[]), :mo, :f, :n, :c, :a) RETURNING id"""),
        {"m": mid, "v": versions, "mo": mode, "f": bool(fill_defaults), "n": (note or "").strip()[:2000], "c": came_from,
         "a": actor}).scalar_one()
    out = []
    for k in kids:
        read_only = k["is_locked"] or k["is_archived"] or k["kind_code"] not in ("project", "template")
        status = "skipped" if read_only else "offered"
        tid = conn.execute(text("""INSERT INTO core.metamodel_push_targets (push_id, model_id, status, error)
                                   VALUES (:p, :m, :s, :e) RETURNING id"""),
                           {"p": push_id, "m": k["id"], "s": status,
                            "e": "read-only model (locked, archived or a reference model)" if read_only else ""}).scalar_one()
        if read_only:
            out.append({"model": k["name"], "status": "skipped"})
            continue
        if mode == "forced":
            res = _apply(conn, tid, actor, how="forced")
            out.append({"model": k["name"], "status": res["status"], "error": res.get("error", "")})
        else:
            notify.create(conn, kind="metamodel.offered", category="metamodel", needs_action=True, model_id=k["id"],
                          actor=actor, include_actor=True, title=f"{m['name']} offers metamodel changes to {k['name']} (versions "
                                             f"{', '.join(map(str, versions))})",
                          body=(note or "") + ("\n" if note else "") + _summary(conn, mid, versions),
                          link=f"#/metamodel/{k['guid']}/pushdown", ref_kind="push_target", ref_id=tid)
            out.append({"model": k["name"], "status": "offered"})
    return {"push": push_id, "versions": versions, "mode": mode, "targets": out,
            "message": f"Pushed versions {', '.join(map(str, versions))} {mode} to {len(kids)} model(s) below."}


def _summary(conn, mid: int, versions: list[int]) -> str:
    notes = [r["note"] for r in _rows(conn, """SELECT note FROM core.metamodel_version_changes WHERE model_id = :m
                                                AND version = ANY (CAST(:v AS integer[])) ORDER BY version, seq""", m=mid, v=versions)]
    return "\n".join(f"- {n}" for n in notes[:30]) + (f"\n... and {len(notes) - 30} more" if len(notes) > 30 else "")


def _target(conn, tid: int) -> dict:
    _bypass(conn, True)    # the child may be a model the parent's Model Admin cannot see (a forced push)
    try:
        t = _one(conn, """SELECT t.*, p.from_model_id, p.versions, p.mode, p.fill_defaults, p.note AS push_note, p.pushed_by,
                             cm.guid AS model_guid, cm.name AS model_name, pm.name AS parent_name
                        FROM core.metamodel_push_targets t JOIN core.metamodel_pushes p ON p.id = t.push_id
                        JOIN core.models cm ON cm.id = t.model_id JOIN core.models pm ON pm.id = p.from_model_id
                       WHERE t.id = :t""", t=tid)
    finally:
        _bypass(conn, False)
    if not t:
        raise PushError("No such pushed package.", 404)
    return t


def _apply(conn, tid: int, actor: str, how: str) -> dict:
    """Makes a package in one child, in a savepoint: a failure leaves the child as it was and is recorded."""
    t = _target(conn, tid)
    ops = _rows(conn, """SELECT op, payload, result FROM core.metamodel_version_changes
                          WHERE model_id = :m AND version = ANY (CAST(:v AS integer[])) ORDER BY version, seq""",
                m=t["from_model_id"], v=list(t["versions"]))
    sp = conn.begin_nested() if hasattr(conn, "begin_nested") else None
    try:
        _bypass(conn, how == "forced")
        changes = []
        for o in ops:
            payload = o["payload"] if isinstance(o["payload"], dict) else json.loads(o["payload"])
            p = _translate(conn, payload, t["from_model_id"], t["model_id"])
            if o["op"] == "attribute.create" and p.get("default_value") not in (None, ""):
                p["apply_default_to_existing"] = bool(t["fill_defaults"])
            changes.append({"op": o["op"], **p})
        # inside the savepoint: a failure rolls the settings back with the change (settings are transactional). Forced,
        # the parent's Model Admin may have no role on the child: it is read past row-level security for this change only
        conn.execute(text("SELECT set_config('eax.push_down', :m, true)"), {"m": str(t["model_id"])})
        result = ed.apply_many(conn, t["model_guid"], changes, actor)
        _bypass(conn, how == "forced")   # (refreshing the report views inside it resets the setting)
        for o, r in zip(ops, result["results"], strict=True):
            pres = o["result"] if isinstance(o["result"], dict) else json.loads(o["result"] or "{}")
            _link_made(conn, pres, r["result"], t["model_id"])
        note = f"From {t['parent_name']} (versions {', '.join(map(str, t['versions']))}): " + result["note"]
        conn.execute(text("UPDATE core.metamodel_versions SET note = :n WHERE model_id = :m AND version = :v"),
                     {"n": note[:1000], "m": t["model_id"], "v": result["version"]})
        conn.execute(text("SELECT set_config('eax.push_down', '', true)"))   # the package is in: back to normal rights
        _bypass(conn, False)
        conn.execute(text("""UPDATE core.metamodel_push_targets SET status = 'applied', decided_by = :a, decided_at = now(),
                                    applied_version = :v, error = '' WHERE id = :t"""),
                     {"a": actor, "v": result["version"], "t": tid})
        if sp is not None:
            sp.commit()
    except (ed.EditError, PushError, DBAPIError) as exc:
        if sp is not None:
            sp.rollback()
        if isinstance(exc, DBAPIError):
            exc = ed.EditError(ed._db_message(exc), 409)
        conn.execute(text("UPDATE core.metamodel_push_targets SET status = 'failed', error = :e, decided_by = :a, decided_at = now() "
                          "WHERE id = :t"), {"e": str(exc)[:1000], "a": actor, "t": tid})
        notify.create(conn, kind="metamodel.failed", category="metamodel", needs_action=True, model_id=t["model_id"],
                      actor=actor, title=f"Metamodel changes from {t['parent_name']} could not be made in {t['model_name']}",
                      body=str(exc), link=f"#/metamodel/{t['model_guid']}/pushdown", ref_kind="push_target", ref_id=tid)
        return {"status": "failed", "error": str(exc)}
    t = _target(conn, tid)
    doc = change_docs.for_push(conn, t["model_id"], {"versions": t["versions"], "note": t["push_note"]}, t,
                               result["results"], result.get("impact") or {}, actor, t["parent_name"], how)
    notify.create(conn, kind="metamodel.applied", category="metamodel", model_id=t["model_id"], actor=actor,
                  include_actor=True,
                  title=f"{t['model_name']} has new metamodel changes from {t['parent_name']} ({how}): version {result['version']}",
                  body=result["note"], link=f"#/change-documents/{doc}", ref_kind="change_document", ref_id=doc)
    kids = [k for k in children(conn, t["model_id"])]
    if kids:   # the child's Model Admins decide whether it goes on down
        notify.create(conn, kind="metamodel.pass_on", category="metamodel", needs_action=True, model_id=t["model_id"],
                      actor=actor, include_actor=True,
                      title=f"Pass the metamodel changes from {t['parent_name']} on to the {len(kids)} model(s) under {t['model_name']}?",
                      body="Push them forced or offered from the Push down tab, or resolve this to keep them here.",
                      link=f"#/metamodel/{t['model_guid']}/pushdown", ref_kind="pass_on", ref_id=tid)
    return {"status": "applied", "version": result["version"], "document": doc}


def decide(conn, model, tid: int, actor: str, accept: bool, note: str = "") -> dict:
    """The child's Model Admin accepts (it is made at once) or rejects (the child diverges) an offered package."""
    m = _model(conn, model)
    t = _target(conn, tid)
    if t["model_id"] != m["_id"]:
        raise PushError("That package was not offered to this model.", 404)
    if t["status"] != "offered":
        raise PushError(f"Already decided: {t['status']}.", 409)
    note = (note or "").strip()
    if accept:
        res = _apply(conn, tid, actor, how="accepted")
        if res["status"] == "applied":
            notify.resolve_ref(conn, "push_target", tid, actor, f"Accepted by {actor}" + (f": {note}" if note else ""))
            conn.execute(text("UPDATE core.metamodel_push_targets SET note = :n WHERE id = :t"), {"n": note, "t": tid})
        return res
    if not note:
        raise PushError("Say why you reject it: the model will differ from its parent, and the note stays in its lineage.")
    conn.execute(text("""UPDATE core.metamodel_push_targets SET status = 'rejected', decided_by = :a, decided_at = now(), note = :n
                         WHERE id = :t"""), {"a": actor, "n": note[:2000], "t": tid})
    notify.resolve_ref(conn, "push_target", tid, actor, f"Rejected by {actor}: {note}")
    p = _one(conn, "SELECT pushed_by FROM core.metamodel_pushes WHERE id = :p", p=t["push_id"])
    notify.create(conn, kind="metamodel.rejected", category="metamodel", model_id=t["from_model_id"], actor=actor,
                  title=f"{t['model_name']} rejected the metamodel changes from {t['parent_name']}", body=note,
                  recipients=sorted(set(notify.model_people(conn, t["from_model_id"])) | {p["pushed_by"]}),
                  link=f"#/metamodel/{_one(conn, 'SELECT guid FROM core.models WHERE id = :m', m=t['from_model_id'])['guid']}/pushdown")
    return {"status": "rejected"}


def pass_on(conn, model, actor: str, mode: str, fill_defaults: bool = True, note: str = "") -> dict:
    """Pushing what arrived on down: an ordinary push of this model's unpushed versions, remembering where it came from."""
    m = _model(conn, model)
    last = _one(conn, """SELECT push_id, id FROM core.metamodel_push_targets WHERE model_id = :m AND status = 'applied'
                          ORDER BY id DESC LIMIT 1""", m=m["_id"])
    out = push(conn, model, actor, mode, fill_defaults, note, came_from=last["push_id"] if last else None)
    if last:
        notify.resolve_ref(conn, "pass_on", last["id"], actor, f"Passed on {mode} by {actor}")
    return out
