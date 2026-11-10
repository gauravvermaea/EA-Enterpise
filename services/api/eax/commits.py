"""Commits of content (build phase 8, D165).

Content (entities, values, relationships; not the metamodel) entered in a working model is private to its
author until it is committed. Each change is recorded, not written:

* record: the change is tried out on top of the author's earlier uncommitted changes (in a savepoint that
  is rolled back), so it is checked exactly as a real save would be and the answer shows the result; then
  it is kept in the author's open change set (core.change_sets, core.pending_changes) with the committed
  state it was made against (base) and what it will make (mine).
* overlay: the author's reads replay their uncommitted changes in a savepoint that is rolled back, so they
  see their own work; nobody else does. Reports, graphs and MCP read the committed tables only.
* request: the author asks for a commit; the model's committers (Committer, Model Sub Admin, Model Admin)
  then see the change set and commit it, reject it or send it back with a note. Someone who may commit can
  commit their own changes straight away; nothing is committed automatically.
* commit: the chosen changes are replayed for real, in order, in one transaction (all or nothing), with a
  history label; changes committed by others meanwhile on the same fields are conflicts the committer
  resolves first (keep theirs, take mine, or a value). Each item keeps the target before and after.
* roll back: a committed commit, whole or item by item, is undone as a new commit (the targets are put
  back as they were before); and the author can discard uncommitted changes, whole set or one by one.

Only working (project) models use commits; library models and roots are curated directly.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import content as ct
from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError

ENTITY_FIELDS = ("name", "description", "parent", "tags", "display_id")
FIELD_NAMES = {"name": "Name", "description": "Description", "parent": "Part of", "tags": "Tags", "display_id": "Display ID",
               "status": "Status", "deleted": "Deleted", "relationships": "Relationships"}


class CommitConflict(EditError):
    """Changes committed meanwhile clash with the changes to commit: each conflict, to be resolved first."""

    def __init__(self, conflicts: list[dict]):
        super().__init__(f"{len(conflicts)} change{'s' if len(conflicts) != 1 else ''} clash with what was committed since "
                         "they were made: resolve them and commit again.", 409)
        self.conflicts = conflicts


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def _one(conn, sql: str, **p) -> dict | None:
    rows = _rows(conn, sql, **p)
    return rows[0] if rows else None


def _exec(conn, sql: str, **p):
    return ct._exec(conn, sql, **p)


def _s(v) -> str | None:
    return None if v is None else str(v)


def _model(conn, model: Any) -> dict:
    return repo.get_model(conn, model)


def uses_commits(m: dict) -> bool:
    """Working models keep content private until committed; library models and roots do not (D165)."""
    return m.get("kind") == "project"


def may_commit(conn, user, m: dict) -> bool:
    if user is None or perms.SUPER_ADMIN in user.roles:
        return True
    return bool(set(perms.model_roles(conn, user.username, m["id"])) & perms.MODEL_PERMISSIONS["model.commit"])


def sees_history(conn, user, m: dict) -> bool:
    if user is None or perms.SUPER_ADMIN in user.roles:
        return True
    return bool(set(perms.model_roles(conn, user.username, m["id"])) & perms.MODEL_PERMISSIONS["model.history"])


# ---------------------------------------------------------------- snapshots: an entity or relationship as it is
def _canon(r: dict) -> str | None:
    if r.get("value_ref") is not None:
        return str(r["ref_guid"]) if r.get("ref_guid") else None
    if r.get("value_text") is not None:
        return str(r["value_text"])
    if r.get("value_number") is not None:
        try:
            return format(Decimal(str(r["value_number"])).normalize(), "f")
        except InvalidOperation:
            return str(r["value_number"])
    if r.get("value_date") is not None:
        v = r["value_date"]
        return v.isoformat() if hasattr(v, "isoformat") else str(v)[:10]
    if r.get("value_bool") is not None:
        return "Yes" if r["value_bool"] in (True, "true", "t", 1) else "No"
    return None


def snap_entity(conn, m: dict, guid: Any) -> dict | None:
    g = repo._as_guid(guid)
    if not g:
        return None
    e = _one(conn, """SELECT e.id, e.guid, e.name, e.description, e.display_id, e.status_code AS status, e.tags, e.is_deleted,
                             p.guid AS parent, t.code AS type_code, t.name AS entity_type
                        FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                        LEFT JOIN core.entities p ON p.id = e.parent_entity_id
                       WHERE e.guid = :g AND e.model_id = :m""", g=str(g), m=m["_id"])
    if not e:
        return None
    vals = _rows(conn, """SELECT av.id, at.code, av.value_text, av.value_number, av.value_date, av.value_bool, av.value_ref,
                                 r.guid AS ref_guid
                            FROM core.attribute_values av JOIN core.attribute_types at ON at.id = av.attribute_type_id
                            LEFT JOIN core.entities r ON r.id = av.value_ref
                           WHERE av.entity_id = :e AND NOT av.is_deleted ORDER BY at.code""", e=e["id"])
    rels = _rows(conn, """SELECT guid FROM core.relationships WHERE NOT is_deleted
                           AND (source_entity_id = :e OR target_entity_id = :e) ORDER BY guid""", e=e["id"])
    tags = e["tags"] or []
    if isinstance(tags, str):
        tags = [t for t in tags.strip("{}").split(",") if t]
    return {"kind": "entity", "guid": str(e["guid"]), "deleted": bool(e["is_deleted"]), "name": e["name"],
            "description": e["description"] or "", "display_id": e["display_id"], "status": e["status"], "tags": sorted(tags),
            "parent": _s(e["parent"]), "type_code": e["type_code"], "entity_type": e["entity_type"],
            "values": {v["code"]: _canon(v) for v in vals if _canon(v) is not None},
            "_value_ids": [v["id"] for v in vals], "relationships": [str(r["guid"]) for r in rels]}


def snap_relationship(conn, m: dict, guid: Any) -> dict | None:
    g = repo._as_guid(guid)
    if not g:
        return None
    r = _one(conn, """SELECT r.guid, r.name, r.is_deleted, rt.code AS type_code, rt.name AS relationship_type, rt.verb,
                             s.guid AS source, s.name AS source_name, t.guid AS target, t.name AS target_name
                        FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
                        JOIN core.entities s ON s.id = r.source_entity_id JOIN core.entities t ON t.id = r.target_entity_id
                       WHERE r.guid = :g AND r.model_id = :m""", g=str(g), m=m["_id"])
    if not r:
        return None
    return {"kind": "relationship", "guid": str(r["guid"]), "deleted": bool(r["is_deleted"]), "name": r["name"] or "",
            "type_code": r["type_code"], "relationship_type": r["relationship_type"], "verb": r["verb"],
            "source": str(r["source"]), "source_name": r["source_name"], "target": str(r["target"]), "target_name": r["target_name"]}


def _snap(conn, m: dict, kind: str, guid: Any) -> dict | None:
    return snap_relationship(conn, m, guid) if kind == "relationship" else snap_entity(conn, m, guid)


def _fields_of(state: dict | None, fields: list[str]) -> dict:
    out = {}
    for f in fields:
        if state is None:
            out[f] = None
        elif f.startswith("value:"):
            out[f] = state["values"].get(f[6:])
        else:
            out[f] = state.get(f)
    return out


def _touched(op: str, args: dict, after: dict | None) -> list[str]:
    if op == "entity.update":
        data = args.get("data") or {}
        fields = [f for f in ENTITY_FIELDS if f in data]
        stored = {c.lower(): c for c in ((after or {}).get("values") or {})}   # attribute codes as the model spells them
        fields += [f"value:{stored.get(str(c).lower(), c)}" for c in (data.get("values") or {})]
        return fields
    if op == "entity.status":
        return ["status"]
    if op == "relationship.rename":
        return ["name"]
    return []


def _same(a, b) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def _content(state: dict | None) -> dict | None:
    """What counts when asking whether a target changed since: everything but internal ids."""
    if state is None:
        return None
    return {k: v for k, v in state.items() if not k.startswith("_")}


# ---------------------------------------------------------------- applying a change
def _apply(conn, m: dict, op: str, args: dict, actor: str) -> dict:
    """Runs one change for real on the connection (the functions of eax.content)."""
    mid = str(m["id"])
    if op == "entity.create":
        return ct.create_entity(conn, mid, args["data"], actor, light=True)
    if op == "entity.update":
        return ct.update_entity(conn, mid, args["entity"], args["data"], actor, light=True)
    if op == "entity.status":
        return ct.set_status(conn, mid, args["entity"], args["status"])
    if op == "entity.delete":
        return ct.delete_entity(conn, mid, args["entity"])
    if op == "entity.rollback":
        return ct.roll_back(conn, mid, args["entity"], int(args["event"]), actor)
    if op == "relationship.create":
        return ct.add_relationship(conn, mid, args["data"], actor)
    if op == "relationship.delete":
        return ct.delete_relationship(conn, mid, args["relationship"])
    if op == "relationship.rename":
        g = repo._as_guid(args["relationship"])
        row = _one(conn, "SELECT id FROM core.relationships WHERE guid = :g AND model_id = :m AND NOT is_deleted",
                   g=str(g), m=m["_id"]) if g else None
        if not row:
            raise EditError("This relationship is no longer there.", 404)
        _exec(conn, "UPDATE core.relationships SET name = :n WHERE id = :i", n=(args.get("name") or "").strip(), i=row["id"])
        return {"id": str(g), "name": args.get("name") or ""}
    raise EditError(f"Unknown change {op!r}.")


def _target(op: str, args: dict) -> tuple[str, str | None]:
    if op == "entity.create":
        return "entity", args["data"].get("guid")
    if op.startswith("entity."):
        return "entity", _s(args.get("entity"))
    if op == "relationship.create":
        return "relationship", args["data"].get("guid")
    return "relationship", _s(args.get("relationship"))


def _label(conn, m: dict, op: str, args: dict, before: dict | None, after: dict | None) -> str:
    st = after or before or {}
    name = st.get("name") or (args.get("data") or {}).get("name") or "?"
    if op == "entity.create":
        return f"New {st.get('entity_type', 'entity')} '{name}'"
    if op == "entity.update":
        fields = [FIELD_NAMES.get(f, f[6:] if f.startswith("value:") else f) for f in _touched(op, args, after)]
        return f"Change {st.get('entity_type', '')} '{name}': {', '.join(fields) or 'no fields'}".replace("Change  '", "Change '")
    if op == "entity.status":
        return f"{'Retire' if args.get('status') == 'retired' else 'Restore'} '{name}'"
    if op == "entity.delete":
        return f"Delete {st.get('entity_type', '')} '{name}'".replace("Delete  '", "Delete '")
    if op == "entity.rollback":
        return f"Roll back '{name}' to an earlier version"
    if st.get("kind") == "relationship":
        rel = f"{st.get('source_name')} {st.get('verb') or st.get('relationship_type')} {st.get('target_name')}"
        return {"relationship.create": f"Relate: {rel}", "relationship.delete": f"Remove relationship: {rel}",
                "relationship.rename": f"Rename relationship: {rel}"}.get(op, op)
    return op


# ---------------------------------------------------------------- the author's change sets
def _open_set(conn, m: dict, author: str) -> int:
    row = _one(conn, "SELECT id FROM core.change_sets WHERE model_id = :m AND author = :a AND status = 'open'",
               m=m["_id"], a=author.lower())
    if row:
        return row["id"]
    return _exec(conn, "INSERT INTO core.change_sets (model_id, author) VALUES (:m, :a) RETURNING id",
                 m=m["_id"], a=author.lower()).scalar_one()


def _my_pending(conn, m: dict, author: str) -> list[dict]:
    return _rows(conn, """SELECT c.id, c.guid, c.op, c.args, c.label FROM core.pending_changes c
                           WHERE c.model_id = :m AND c.author = :a AND c.status = 'pending' ORDER BY c.id""",
                 m=m["_id"], a=author.lower())


def _json(v) -> Any:
    return v if isinstance(v, (dict, list)) or v is None else json.loads(v)


def _replay(conn, m: dict, author: str, changes: list[dict] | None = None) -> int:
    """Applies the author's uncommitted changes, each in its own savepoint (one that no longer fits is left
    out). The caller rolls the whole replay back. Returns how many applied."""
    n = 0
    for ch in changes if changes is not None else _my_pending(conn, m, author):
        sp = conn.begin_nested()
        try:
            _apply(conn, m, ch["op"], _json(ch["args"]), author)
            sp.commit()
            n += 1
        except (EditError, repo.NotFound, DBAPIError):
            sp.rollback()
    return n


def has_pending(conn, model: Any, author: str) -> bool:
    m = _model(conn, model)
    return bool(_one(conn, "SELECT 1 AS x FROM core.pending_changes WHERE model_id = :m AND author = :a AND status = 'pending' LIMIT 1",
                     m=m["_id"], a=author.lower()))


def overlay(conn, model: Any, author: str, fn):
    """fn(conn) as the author sees the model: committed content with their own uncommitted changes on top."""
    m = _model(conn, model)
    if not uses_commits(m):
        return fn(conn)
    pending = _my_pending(conn, m, author)
    if not pending:
        return fn(conn)
    sp = conn.begin_nested()
    try:
        _replay(conn, m, author, pending)
        out = fn(conn)
    finally:
        sp.rollback()
    marks = pending_marks(conn, m, author)
    if isinstance(out, dict) and isinstance(out.get("rows"), list):
        for r in out["rows"]:
            k = marks["by_target"].get(str(r.get("id")))
            if k:
                r["pending"] = k
        out["pending_changes"] = marks["count"]
    elif isinstance(out, dict) and out.get("id") is not None:
        k = marks["by_target"].get(str(out["id"]))
        if k:
            out["pending"] = k
        out["pending_changes"] = marks["count"]
    return out


def pending_marks(conn, m: dict, author: str) -> dict:
    by: dict[str, str] = {}
    rows = _rows(conn, """SELECT op, target FROM core.pending_changes WHERE model_id = :m AND author = :a AND status = 'pending'
                           ORDER BY id""", m=m["_id"], a=author.lower())
    for r in rows:
        t = _s(r["target"])
        if not t:
            continue
        kind = "created" if r["op"].endswith(".create") else "deleted" if r["op"].endswith(".delete") else "changed"
        if by.get(t) == "created" and kind == "changed":
            continue
        by[t] = kind
    return {"count": len(rows), "by_target": by}


# ---------------------------------------------------------------- recording changes
def _resolve_refs(conn, m: dict, op: str, args: dict) -> dict:
    """Entities given by display ID or name become guids, so the change means the same thing when committed."""
    def guid_of(ref):
        if ref in (None, ""):
            return ref
        eid = ct._entity_id(conn, m, ref)
        return str(_one(conn, "SELECT guid FROM core.entities WHERE id = :e", e=eid)["guid"])
    data = dict(args.get("data") or {})
    if op in ("entity.create", "entity.update") and data.get("parent") not in (None, ""):
        data["parent"] = guid_of(data["parent"])
    if op == "relationship.create":
        data["source"], data["target"] = guid_of(data.get("source")), guid_of(data.get("target"))
    if "entity" in args and args["entity"] not in (None, ""):
        args = {**args, "entity": guid_of(args["entity"])}
    if "relationship" in args:
        g = repo._as_guid(args["relationship"])
        if not g:
            raise EditError("Give the relationship by its id.", 404)
        args = {**args, "relationship": str(g)}
    return {**args, "data": data} if "data" in args else args


def _prepare(op: str, args: dict) -> dict:
    args = json.loads(json.dumps(args, default=str))
    data = args.get("data")
    if isinstance(data, dict):
        data.pop("row_version", None)   # conflicts are found at commit instead (D165)
        if op in ("entity.create", "relationship.create") and not data.get("guid"):
            data["guid"] = str(uuid.uuid4())
    return args


def _try(conn, m: dict, author: str, op: str, args: dict) -> tuple[dict, dict, dict | None, dict | None]:
    """Inside the replayed overlay: resolves references, runs the change and reads the target before and after."""
    args = _resolve_refs(conn, m, op, args)
    kind, target = _target(op, args)
    before = _snap(conn, m, kind, target) if target else None
    out = _apply(conn, m, op, args, author)
    if not target:
        target = _s(out.get("id"))
    after = _snap(conn, m, kind, target) if target else None
    return args, out, before, after


def _rule_warnings(out: Any) -> list[dict]:
    """The rules the changed entity fails, from what the save answered (the entity page's warnings, or a grid row's)."""
    if not isinstance(out, dict):
        return []
    ws = out.get("warnings") if isinstance(out.get("warnings"), list) else out.get("saved_warnings") or []
    return [{"field": w.get("field") or w.get("code") or "", "message": w.get("message") or "", "severity": w.get("severity") or "warning"}
            for w in ws if isinstance(w, dict)][:20]


def _keep(conn, m: dict, author: str, op: str, args: dict, base: dict | None, before: dict | None, after: dict | None,
          warnings: list[dict] | None = None) -> dict:
    kind, target = _target(op, args)
    target = target or (after or {}).get("guid")
    touched = _touched(op, args, after)
    mine = _fields_of(after, touched) if touched else _content(after)
    label = _label(conn, m, op, args, before, after)
    cs = _open_set(conn, m, author)
    row = _exec(conn, """INSERT INTO core.pending_changes (change_set_id, model_id, author, op, args, base, mine, target, target_kind, label,
                                                            warnings)
                         VALUES (:cs, :m, :a, :op, CAST(:args AS jsonb), CAST(:base AS jsonb), CAST(:mine AS jsonb),
                                 CAST(:t AS uuid), :k, :l, CAST(:w AS jsonb)) RETURNING guid""", w=json.dumps(warnings or []),
                cs=cs, m=m["_id"], a=author.lower(), op=op, args=json.dumps(args, default=str),
                base=json.dumps(base, default=str) if base is not None else None,
                mine=json.dumps(mine, default=str) if mine is not None else None, t=target, k=kind, l=label).scalar_one()
    _exec(conn, "UPDATE core.change_sets SET modified_at = now() WHERE id = :i", i=cs)
    return {"change": str(row), "label": label, "target": target}


def _base_for(conn, m: dict, op: str, args: dict) -> dict | None:
    """The committed state a change is made against (read before the overlay): the fields it touches, or
    the whole target for deletes and roll backs. None for something not committed yet."""
    kind, target = _target(op, args)
    if not target or op.endswith(".create"):
        return None
    try:
        g = ct._entity_id(conn, m, target) if kind == "entity" else None
        if kind == "entity" and g:
            target = str(_one(conn, "SELECT guid FROM core.entities WHERE id = :e", e=g)["guid"])
    except EditError:
        return None
    state = _snap(conn, m, kind, target)
    if state is None:
        return None
    if op in ("entity.delete", "entity.rollback", "relationship.delete"):
        return _content(state)
    return {"_state": _content(state)}


def record(conn, model: Any, author: str, op: str, args: dict, answer: str = "result") -> dict:
    """Keeps one change of the author as uncommitted (checked first, exactly as a save). The answer is
    what the save would have answered, marked pending, with the change's id and label."""
    m = _model(conn, model)
    args = _prepare(op, args)
    base = _base_for(conn, m, op, args)
    sp = conn.begin_nested()
    try:
        _replay(conn, m, author)
        args, out, before, after = _try(conn, m, author, op, args)
        warnings = _rule_warnings(out)
        if (after or {}).get("kind") == "entity" and not after["deleted"]:
            detail = repo.get_entity_detail(conn, str(m["id"]), after["guid"])
            warnings = _rule_warnings(detail)   # every rule the entity fails with this change, not only the changed fields
            if answer == "entity":
                out = detail
    finally:
        sp.rollback()
    if base is not None and "_state" in base:
        base = _fields_of(base["_state"], _touched(op, args, after))
    kept = _keep(conn, m, author, op, args, base, before, after, warnings)
    out = dict(out) if isinstance(out, dict) else {"result": out}
    out.update(pending=True, change=kept["change"], change_label=kept["label"],
               note="Saved as an uncommitted change: only you see it until it is committed (Changes tab).")
    return out


def record_many(conn, model: Any, author: str, items: list[tuple[str, dict]]) -> list[dict]:
    """Records several changes (a grid save): each checked on its own; one that fails is reported, the others kept."""
    m = _model(conn, model)
    prepared = [(op, _prepare(op, args)) for op, args in items]
    bases = []
    for op, args in prepared:
        try:
            bases.append(_base_for(conn, m, op, args))
        except (EditError, repo.NotFound):
            bases.append(None)
    results: list[dict] = []
    keep = []
    outer = conn.begin_nested()
    try:
        _replay(conn, m, author)
        for i, (op, args) in enumerate(prepared):
            sp = conn.begin_nested()
            try:
                args2, out, before, after = _try(conn, m, author, op, args)
                sp.commit()
                keep.append((i, op, args2, before, after, _rule_warnings(out)))
                results.append({"ok": True, "out": out, "after": after})
            except (EditError, repo.NotFound) as exc:
                sp.rollback()
                results.append({"ok": False, "error": str(exc)})
    finally:
        outer.rollback()
    for i, op, args, before, after, warnings in keep:
        base = bases[i]
        if base is not None and "_state" in base:
            base = _fields_of(base["_state"], _touched(op, args, after))
        results[i]["kept"] = _keep(conn, m, author, op, args, base, before, after, warnings)
    return results


# ---------------------------------------------------------------- grids record row by row (phase 7 grids, D165)
def record_entity_rows(conn, model: Any, entity_type: Any, rows: list[dict], author: str) -> dict:
    if len(rows) > 5000:
        raise EditError("Save at most 5,000 rows at a time.")
    m = _model(conn, model)
    et = repo._find_type(conn, m["_id"], entity_type)
    items = []
    for r in rows:
        if r.get("id") and r.get("delete"):
            items.append(("entity.delete", {"entity": r["id"]}))
        elif r.get("id"):
            items.append(("entity.update", {"entity": r["id"], "data": {k: v for k, v in r.items() if k not in ("id", "delete")}}))
        else:
            items.append(("entity.create", {"data": {**{k: v for k, v in r.items() if k != "delete"}, "entity_type": str(et["id"])}}))
    out, saved, failed = [], 0, 0
    for i, res in enumerate(record_many(conn, m["id"], author, items), start=1):
        op, args = items[i - 1]
        if res["ok"]:
            saved += 1
            after = res.get("after") or {}
            out.append({"row": i, "ok": True, "id": after.get("guid") or args.get("entity"), "display_id": after.get("display_id"),
                        "warnings": (res["out"] or {}).get("saved_warnings", []), "pending": True,
                        "created": op == "entity.create", "deleted": op == "entity.delete", "change": res["kept"]["change"]})
        else:
            failed += 1
            out.append({"row": i, "ok": False, "error": res["error"], "id": args.get("entity")})
    return {"saved": saved, "failed": failed, "rows": out, "pending": True,
            "note": "Saved as uncommitted changes: only you see them until they are committed (Changes tab)."}


def record_relationship_rows(conn, model: Any, rows: list[dict], author: str) -> dict:
    if len(rows) > 5000:
        raise EditError("Save at most 5,000 rows at a time.")
    m = _model(conn, model)
    items, owner = [], []
    for i, r in enumerate(rows, start=1):
        if r.get("id") and r.get("delete"):
            items.append(("relationship.delete", {"relationship": r["id"]}))
            owner.append(i)
            continue
        if r.get("id"):
            cur = _one(conn, """SELECT r.name, rt.guid AS type, s.guid AS source, t.guid AS target
                                  FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
                                  JOIN core.entities s ON s.id = r.source_entity_id JOIN core.entities t ON t.id = r.target_entity_id
                                 WHERE r.guid = :g AND r.model_id = :m""", g=str(repo._as_guid(r["id"])), m=m["_id"]) \
                if repo._as_guid(r["id"]) else None
            ends_changed = cur is not None and any(k in r and r[k] not in (None, "") and str(r[k]) != str(cur[k])
                                                   for k in ("relationship_type", "source", "target"))
            if ends_changed:
                items.append(("relationship.create", {"data": {
                    "relationship_type": r.get("relationship_type") or str(cur["type"]), "source": r.get("source") or str(cur["source"]),
                    "target": r.get("target") or str(cur["target"]), "name": r.get("name", cur["name"]),
                    "allow_outside": r.get("allow_outside")}}))
                owner.append(i)
                items.append(("relationship.delete", {"relationship": r["id"]}))
                owner.append(i)
            else:
                items.append(("relationship.rename", {"relationship": r["id"], "name": r.get("name") or ""}))
                owner.append(i)
            continue
        items.append(("relationship.create", {"data": {k: r.get(k) for k in ("relationship_type", "source", "target", "name",
                                                                              "allow_outside")}}))
        owner.append(i)
    results = record_many(conn, m["id"], author, items)
    by_row: dict[int, dict] = {}
    for (op, _args), res, i in zip(items, results, owner, strict=True):
        cur = by_row.setdefault(i, {"row": i, "ok": True, "pending": True})
        if not res["ok"]:
            cur.update(ok=False, error=res["error"], outside_metamodel="does not allow" in res["error"])
        elif op == "relationship.create":
            cur.update(id=(res.get("after") or {}).get("guid"), created=True, note=(res["out"] or {}).get("note"))
        elif op == "relationship.delete" and "id" not in cur:
            cur.update(id=rows[i - 1].get("id"), deleted=True)
        else:
            cur.setdefault("id", rows[i - 1].get("id"))
    out = [by_row[i] for i in sorted(by_row)]
    return {"saved": sum(1 for r in out if r["ok"]), "failed": sum(1 for r in out if not r["ok"]), "rows": out, "pending": True,
            "note": "Saved as uncommitted changes: only you see them until they are committed (Changes tab)."}


# ---------------------------------------------------------------- the changes page
def _change_out(conn, m: dict, ch: dict, with_conflicts: bool = False) -> dict:
    base, mine = _json(ch.get("base")), _json(ch.get("mine"))
    rows = []
    if ch["op"] in ("entity.update", "entity.status", "relationship.rename") and isinstance(mine, dict):
        for f, v in mine.items():
            b = (base or {}).get(f) if base else None
            if base and _same(b, v):
                continue   # set to what it already was
            rows.append({"field": FIELD_NAMES.get(f, f[6:] if f.startswith("value:") else f), "code": f, "before": b, "after": v})
    elif ch["op"].endswith(".create") and isinstance(mine, dict):
        if mine.get("kind") == "entity":
            rows = [{"field": "Name", "code": "name", "before": None, "after": mine.get("name")}]
            rows += [{"field": k, "code": f"value:{k}", "before": None, "after": v} for k, v in (mine.get("values") or {}).items()]
            if mine.get("description"):
                rows.insert(1, {"field": "Description", "code": "description", "before": None, "after": mine["description"]})
        else:
            rows = [{"field": "Relationship", "code": "relationship", "before": None,
                     "after": f"{mine.get('source_name')} {mine.get('verb') or mine.get('relationship_type')} {mine.get('target_name')}"}]
    args = _json(ch.get("args")) or {}
    d = args.get("data") or {}
    ents = [x for x in ([_s(ch.get("target"))] if ch.get("target_kind") == "entity" else
                        [_s(d.get("source")), _s(d.get("target")), (mine or {}).get("source") if isinstance(mine, dict) else None,
                         (mine or {}).get("target") if isinstance(mine, dict) else None,
                         (base or {}).get("source") if isinstance(base, dict) else None,
                         (base or {}).get("target") if isinstance(base, dict) else None]) if x]
    out = {"id": str(ch["guid"]), "op": ch["op"], "label": ch["label"], "target": _s(ch.get("target")),
           "entities": sorted(set(ents)), "entity": ents[0] if ents else None, "change_set": None,
           "target_kind": ch.get("target_kind"), "status": ch["status"], "created_at": ch["created_at"], "note": ch.get("note") or "",
           "source": ch.get("source") or "", "author": ch.get("author"), "rows": rows, "warnings": _json(ch.get("warnings")) or []}
    if with_conflicts:
        c = _conflict(conn, m, ch, None)
        out["conflict"] = c
    return out


def _set_out(conn, m: dict, s: dict, changes: list[dict], with_conflicts: bool = False) -> dict:
    return {"id": str(s["guid"]), "author": s["author"], "status": s["status"], "request_note": s["request_note"],
            "reply_note": s["reply_note"], "replied_by": s.get("replied_by"), "requested_at": s.get("requested_at"),
            "modified_at": s["modified_at"], "changes": [{**_change_out(conn, m, c, with_conflicts), "change_set": str(s["guid"])}
                                                         for c in changes]}


def changes_page(conn, model: Any, user, entity: Any = None) -> dict:
    """The Changes tab: my uncommitted changes by change set, the requests waiting for me (if I commit), and
    whether I may commit. With an entity: only the changes to it and its relationships (the entity page)."""
    m = _model(conn, model)
    me = user.username.lower()
    committer = may_commit(conn, user, m)
    want = None
    if entity:
        want = _s(entity) if repo._as_guid(entity) else None
        if want is None:
            e = _one(conn, "SELECT guid FROM core.entities WHERE model_id = :m AND (display_id = :r OR lower(name) = lower(:r)) LIMIT 1",
                     m=m["_id"], r=str(entity))
            want = _s(e["guid"]) if e else "-"
    sets = _rows(conn, """SELECT s.* FROM core.change_sets s WHERE s.model_id = :m AND s.status <> 'closed'
                           AND (s.author = :a OR (:c AND s.status = 'requested'))
                         ORDER BY (s.author = :a) DESC, s.requested_at NULLS FIRST, s.id""", m=m["_id"], a=me, c=committer)
    changes = _rows(conn, """SELECT c.* FROM core.pending_changes c WHERE c.change_set_id = ANY (:s) AND c.status = 'pending'
                              ORDER BY c.id""", s=[s["id"] for s in sets]) if sets else []
    mine, requests = [], []
    for s in sets:
        these = [c for c in changes if c["change_set_id"] == s["id"]]
        if not these:
            continue
        out = _set_out(conn, m, s, these, with_conflicts=committer)
        if entity:
            out["changes"] = [c for c in out["changes"] if want in c["entities"]]
            if not out["changes"]:
                continue
        (mine if s["author"] == me else requests).append(out)
    for group in (mine, requests):   # the rules a target fails: as its author's last change to it leaves it
        last: dict = {}
        for s_ in group:
            for c in s_["changes"]:
                if c["target"]:
                    if c["target"] in last:
                        last[c["target"]]["warnings"] = []
                    last[c["target"]] = c
    decided = _rows(conn, """SELECT c.guid AS id, c.label, c.status, c.note, c.decided_by, c.decided_at, k.number AS commit
                               FROM core.pending_changes c LEFT JOIN core.commits k ON k.id = c.commit_id
                              WHERE c.model_id = :m AND c.author = :a AND c.status IN ('committed', 'rejected')
                                AND c.decided_at > now() - interval '30 days'
                              ORDER BY c.decided_at DESC, c.id DESC LIMIT 100""", m=m["_id"], a=me)
    for d in decided:
        d["id"] = str(d["id"])
    return {"model": {"id": str(m["id"]), "name": m["name"]}, "uses_commits": uses_commits(m), "may_commit": committer,
            "sees_history": sees_history(conn, user, m), "mine": mine, "requests": requests, "decided": decided,
            "pending_count": sum(len(s["changes"]) for s in mine)}


def _set_row(conn, m: dict, set_id: Any) -> dict:
    g = repo._as_guid(set_id)
    s = _one(conn, "SELECT * FROM core.change_sets WHERE guid = :g AND model_id = :m", g=str(g), m=m["_id"]) if g else None
    if not s:
        raise EditError("No such change set in this model.", 404)
    return s


def _close_if_done(conn, set_id: int) -> None:
    _exec(conn, """UPDATE core.change_sets SET status = 'closed', modified_at = now() WHERE id = :i AND NOT EXISTS (
                     SELECT 1 FROM core.pending_changes WHERE change_set_id = :i AND status = 'pending')""", i=set_id)


def request_commit(conn, model: Any, user, set_id: Any = None, note: str = "", change_ids: list | None = None) -> dict:
    """The author asks the model's committers to commit their open (or sent back) change set; or only the
    chosen changes (for example those to one entity, from the entity page), which move to a set of their own."""
    m = _model(conn, model)
    me = user.username.lower()
    if change_ids:
        rows = _changes_for(conn, m, user, None, change_ids, purpose="discard")
        if any(r["author"] != me for r in rows):
            raise EditError("Ask for a commit of your own changes only.", 403)
        sid = _exec(conn, """INSERT INTO core.change_sets (model_id, author, status, request_note, requested_at)
                             VALUES (:m, :a, 'requested', :n, now()) RETURNING id""",
                    m=m["_id"], a=me, n=(note or "").strip()).scalar_one()
        old = {r["change_set_id"] for r in rows}
        _exec(conn, "UPDATE core.pending_changes SET change_set_id = :s WHERE id = ANY (:i)", s=sid, i=[r["id"] for r in rows])
        for o in old:
            _close_if_done(conn, o)
        return {"requested": str(_one(conn, "SELECT guid FROM core.change_sets WHERE id = :i", i=sid)["guid"]), "changes": len(rows)}
    if set_id:
        s = _set_row(conn, m, set_id)
    else:
        s = _one(conn, """SELECT * FROM core.change_sets WHERE model_id = :m AND author = :a AND status IN ('open', 'returned')
                          ORDER BY (status = 'open') DESC, id DESC LIMIT 1""", m=m["_id"], a=me)
    if not s or s["author"] != me:
        raise EditError("You have no uncommitted changes here to ask a commit for.", 404)
    if s["status"] == "requested":
        raise EditError("A commit is already requested for these changes.", 409)
    if not _one(conn, "SELECT 1 AS x FROM core.pending_changes WHERE change_set_id = :i AND status = 'pending'", i=s["id"]):
        raise EditError("This change set has no uncommitted changes.", 409)
    if s["status"] == "returned":   # the changes made since it came back go with it
        o = _one(conn, "SELECT id FROM core.change_sets WHERE model_id = :m AND author = :a AND status = 'open'", m=m["_id"], a=me)
        if o:
            _exec(conn, "UPDATE core.pending_changes SET change_set_id = :s WHERE change_set_id = :o AND status = 'pending'",
                  s=s["id"], o=o["id"])
            _exec(conn, "UPDATE core.change_sets SET status = 'closed' WHERE id = :o", o=o["id"])
    _exec(conn, """UPDATE core.change_sets SET status = 'requested', request_note = :n, requested_at = now(), modified_at = now()
                   WHERE id = :i""", n=(note or "").strip(), i=s["id"])
    return {"requested": str(s["guid"])}


def withdraw_request(conn, model: Any, user, set_id: Any) -> dict:
    m = _model(conn, model)
    s = _set_row(conn, m, set_id)
    if s["author"] != user.username.lower() or s["status"] != "requested":
        raise EditError("Only the author withdraws their own request.", 403)
    _exec(conn, """UPDATE core.change_sets SET status = CASE WHEN EXISTS (SELECT 1 FROM core.change_sets o WHERE o.model_id = :m
                     AND o.author = :a AND o.status = 'open') THEN 'returned' ELSE 'open' END, modified_at = now() WHERE id = :i""",
          i=s["id"], m=m["_id"], a=s["author"])
    return {"withdrawn": str(s["guid"])}


def send_back(conn, model: Any, user, set_id: Any, note: str) -> dict:
    """A committer sends a requested change set back to its author with a note."""
    m = _model(conn, model)
    if not may_commit(conn, user, m):
        raise EditError("Sending changes back needs the Committer, Model Sub Admin or Model Admin role on this model.", 403)
    s = _set_row(conn, m, set_id)
    if s["status"] != "requested":
        raise EditError("Only changes waiting for a commit are sent back.", 409)
    if not (note or "").strip():
        raise EditError("Say what to change.")
    _exec(conn, """UPDATE core.change_sets SET status = 'returned', reply_note = :n, replied_by = :u, replied_at = now(),
                   modified_at = now() WHERE id = :i""", n=note.strip(), u=user.username.lower(), i=s["id"])
    return {"sent_back": str(s["guid"])}


def _changes_for(conn, m: dict, user, set_id: Any = None, change_ids: list | None = None, purpose: str = "commit") -> list[dict]:
    """The pending changes a person may act on: their own; or, for a committer, those of a requested set."""
    me = user.username.lower()
    where, p = ["c.model_id = :m", "c.status = 'pending'"], {"m": m["_id"]}
    if set_id:
        s = _set_row(conn, m, set_id)
        where.append("c.change_set_id = :s")
        p["s"] = s["id"]
        if s["author"] != me and not (s["status"] == "requested" and may_commit(conn, user, m) and purpose != "discard"):
            raise EditError("You may act only on your own changes, or as a committer on changes someone asked to commit.", 403)
    else:
        where.append("c.author = :a")
        p["a"] = me
    rows = _rows(conn, f"SELECT c.* FROM core.pending_changes c WHERE {' AND '.join(where)} ORDER BY c.id", **p)
    if change_ids:
        want = {str(repo._as_guid(x)) for x in change_ids if repo._as_guid(x)}
        rows = [r for r in rows if str(r["guid"]) in want]
        if len(rows) != len(want):
            raise EditError("Some of those changes are not waiting any more (or are not yours to act on).", 409)
    if not rows:
        raise EditError("No uncommitted changes to act on.", 409)
    return rows


def discard(conn, model: Any, user, set_id: Any = None, change_ids: list | None = None) -> dict:
    """The author discards their own uncommitted changes (rolled back before commit): whole set or chosen ones."""
    m = _model(conn, model)
    rows = _changes_for(conn, m, user, set_id, change_ids, purpose="discard")
    if any(r["author"] != user.username.lower() for r in rows):
        raise EditError("Only the author discards their changes; a committer rejects them.", 403)
    ids = [r["id"] for r in rows]
    _exec(conn, """UPDATE core.pending_changes SET status = 'discarded', decided_by = :u, decided_at = now()
                   WHERE id = ANY (:i)""", u=user.username.lower(), i=ids)
    for sid in {r["change_set_id"] for r in rows}:
        _close_if_done(conn, sid)
    return {"discarded": len(ids)}


def reject(conn, model: Any, user, set_id: Any, change_ids: list | None = None, note: str = "") -> dict:
    """A committer rejects requested changes (whole set or chosen ones); they never reach the model."""
    m = _model(conn, model)
    if not may_commit(conn, user, m):
        raise EditError("Rejecting changes needs the Committer, Model Sub Admin or Model Admin role on this model.", 403)
    rows = _changes_for(conn, m, user, set_id, change_ids)
    ids = [r["id"] for r in rows]
    _exec(conn, """UPDATE core.pending_changes SET status = 'rejected', note = :n, decided_by = :u, decided_at = now()
                   WHERE id = ANY (:i)""", n=(note or "").strip(), u=user.username.lower(), i=ids)
    for sid in {r["change_set_id"] for r in rows}:
        _exec(conn, "UPDATE core.change_sets SET reply_note = :n, replied_by = :u, replied_at = now() WHERE id = :i",
              n=(note or "").strip(), u=user.username.lower(), i=sid)
        _close_if_done(conn, sid)
    return {"rejected": len(ids)}


# ---------------------------------------------------------------- conflicts and commit
def _conflict(conn, m: dict, ch: dict, resolution: Any) -> dict | None:
    """What clashes between a change and the content committed since it was made; None when nothing does
    (or the resolution settles it)."""
    op, args = ch["op"], _json(ch["args"])
    base, mine = _json(ch.get("base")), _json(ch.get("mine"))
    kind, target = _target(op, args)
    out = {"change": str(ch["guid"]), "label": ch["label"], "op": op, "author": ch["author"], "target_kind": ch.get("target_kind"),
           "entity": _s(ch.get("target")) if ch.get("target_kind") == "entity"
           else _s((args.get("data") or {}).get("source")) or _s(((mine if isinstance(mine, dict) else None) or base or {}).get("source"))}
    if op == "relationship.create":
        d = args["data"]
        ends = [snap_entity(conn, m, d.get("source")), snap_entity(conn, m, d.get("target"))]
        pending_ends = {_s(x["target"]) for x in _rows(conn, """SELECT target FROM core.pending_changes WHERE model_id = :m
                         AND status = 'pending' AND op = 'entity.create'""", m=m["_id"])}
        if any((e is None and str(d.get(k)) not in pending_ends) or (e is not None and e["deleted"])
               for e, k in zip(ends, ("source", "target"), strict=True)):
            if resolution == "skip":
                return None
            return {**out, "kind": "gone", "message": "One of the two entities was deleted since: this relationship cannot be added.",
                    "choices": ["skip"]}
        return None
    if op.endswith(".create"):
        return None
    cur = _snap(conn, m, kind, target)
    if cur is None or cur["deleted"]:
        if op in ("entity.delete", "relationship.delete"):
            return None   # already gone: nothing to do
        if resolution == "skip":
            return None
        return {**out, "kind": "gone", "message": "It was deleted since this change was made.", "choices": ["skip"]}
    if op in ("entity.delete", "entity.rollback", "relationship.delete"):
        if base is None or _same(_content(base), _content(cur)) or resolution in ("mine", "skip"):
            return None
        return {**out, "kind": "changed", "choices": ["mine", "skip"],
                "message": "It was changed by someone else since this change was made.",
                "fields": [{"field": FIELD_NAMES.get(f, f[6:] if f.startswith("value:") else f), "code": f,
                            "base": b, "theirs": c} for f, b, c in _differences(base, cur)]}
    if not isinstance(mine, dict) or base is None or resolution == "mine":
        return None
    fields = []
    res = resolution.get("fields", {}) if isinstance(resolution, dict) else {}
    if resolution == "skip":
        return None
    for f, want in mine.items():
        b = base.get(f)
        c = _fields_of(cur, [f])[f]
        if not _same(b, c) and not _same(want, c) and f not in res:
            fields.append({"field": FIELD_NAMES.get(f, f[6:] if f.startswith("value:") else f), "code": f,
                           "base": b, "theirs": c, "mine": want})
    if not fields:
        return None
    return {**out, "kind": "fields", "fields": fields, "choices": ["mine", "theirs", "value", "skip"],
            "message": "Someone else committed a different value since this change was made."}


def _differences(a: dict, b: dict) -> list[tuple[str, Any, Any]]:
    out = []
    for f in ("name", "description", "parent", "tags", "display_id", "status", "deleted"):
        if f in a or f in b:
            if not _same(a.get(f), b.get(f)):
                out.append((f, a.get(f), b.get(f)))
    av, bv = a.get("values") or {}, b.get("values") or {}
    for c in sorted({*av, *bv}):
        if not _same(av.get(c), bv.get(c)):
            out.append((f"value:{c}", av.get(c), bv.get(c)))
    return out


def _resolved_args(ch: dict, resolution: Any) -> dict:
    args = _json(ch["args"])
    if not isinstance(resolution, dict) or ch["op"] != "entity.update":
        return args
    data = dict(args.get("data") or {})
    values = dict(data.get("values") or {})
    for f, how in (resolution.get("fields") or {}).items():
        key = f[6:] if f.startswith("value:") else f
        if how == "theirs":
            if f.startswith("value:"):
                for k in list(values):
                    if k.lower() == key.lower():
                        values.pop(k)
            else:
                data.pop(key, None)
        elif isinstance(how, dict) and "value" in how:
            if f.startswith("value:"):
                values = {k: v for k, v in values.items() if k.lower() != key.lower()}
                values[key] = how["value"]
            else:
                data[key] = how["value"]
    if values or "values" in data:
        data["values"] = values
    return {**args, "data": data}


def _dependencies(conn, m: dict, chosen: list[dict]) -> None:
    """A change that needs an entity another, not chosen, uncommitted change creates cannot go alone."""
    creators = {_s(r["target"]): r for r in _rows(conn, """SELECT guid, target, label FROM core.pending_changes
                  WHERE model_id = :m AND status = 'pending' AND op IN ('entity.create', 'relationship.create')""", m=m["_id"])}
    picked = {str(c["guid"]) for c in chosen}
    missing = []
    for c in chosen:
        args = _json(c["args"])
        d = args.get("data") or {}
        refs = [args.get("entity"), args.get("relationship"), d.get("parent"), d.get("source"), d.get("target")]
        for r in refs:
            cr = creators.get(_s(r))
            if cr and str(cr["guid"]) not in picked and _s(cr["target"]) != _s(c.get("target")):
                missing.append(f"'{c['label']}' needs '{cr['label']}'")
    if missing:
        raise EditError("Commit these together: " + "; ".join(sorted(set(missing))[:10]) + ".", 409)


def _history_label(conn, text_: str) -> None:
    conn.execute(text("SELECT set_config('eax.history_label', :l, true)"), {"l": text_[:300]})


def _new_commit(conn, m: dict, user, kind: str, message: str, authors: list[str], rolls_back: int | None = None) -> dict:
    n = (_one(conn, "SELECT coalesce(max(number), 0) + 1 AS n FROM core.commits WHERE model_id = :m", m=m["_id"]) or {"n": 1})["n"]
    row = _one(conn, """INSERT INTO core.commits (model_id, number, kind, message, committed_by, authors, rolls_back)
                        VALUES (:m, :n, :k, :msg, :u, CAST(:a AS text[]), :r) RETURNING id, guid, number""",
               m=m["_id"], n=n, k=kind, msg=(message or "").strip(), u=user.username.lower(), a=sorted(set(authors)), r=rolls_back)
    _history_label(conn, f"Commit {row['number']}{' (roll back)' if kind == 'rollback' else ''}: {(message or '').strip()}"
                         f" (by {user.username}; changes by {', '.join(sorted(set(authors)))})")
    return row


def _item(conn, commit_id: int, change_id: int | None, author: str, op: str, args: dict, kind: str, target: str | None,
          label: str, before: dict | None, after: dict | None) -> None:
    _exec(conn, """INSERT INTO core.commit_items (commit_id, change_id, author, op, args, target, target_kind, label, before, after)
                   VALUES (:c, :ch, :a, :op, CAST(:args AS jsonb), CAST(:t AS uuid), :k, :l, CAST(:b AS jsonb), CAST(:af AS jsonb))""",
          c=commit_id, ch=change_id, a=author, op=op, args=json.dumps(args, default=str), t=target, k=kind, l=label,
          b=json.dumps(before, default=str) if before is not None else None,
          af=json.dumps(after, default=str) if after is not None else None)


def commit(conn, model: Any, user, set_id: Any = None, change_ids: list | None = None, resolutions: dict | None = None,
           message: str = "", relationships_only: bool = False) -> dict:
    """Commits uncommitted changes: the committer's own (no set given) or a requested change set, all of it
    or the chosen changes. Conflicts with content committed since must be resolved first (CommitConflict).
    All or nothing; each item keeps the target before and after for a later roll back.
    relationships_only (a drawn view, D413): anyone who may change the model commits their own relationships and
    junctions straight away; any other change among them still needs a committer."""
    m = _model(conn, model)
    if relationships_only and not set_id:
        rows = _changes_for(conn, m, user, None, change_ids)
        if all(drawn_free(conn, m, r["op"], _json(r["args"]) or {}) for r in rows):
            return _commit_rows(conn, m, user, rows, resolutions, message)
    if not may_commit(conn, user, m):
        raise EditError("Committing needs the Committer, Model Sub Admin or Model Admin role on this model. "
                        "Ask for a commit instead: the model's committers will see your changes.", 403)
    rows = _changes_for(conn, m, user, set_id, change_ids)
    return _commit_rows(conn, m, user, rows, resolutions, message)


def drawn_free(conn, m: dict, op: str, args: dict) -> bool:
    """What a drawn view commits without a committer (D413): relationships, and junctions (connectors, not content)."""
    if op.startswith("relationship."):
        return True
    if op == "entity.create":
        try:
            et = repo._find_type(conn, m["_id"], (args.get("data") or {}).get("entity_type"))
        except repo.NotFound:
            return False
        return bool(et.get("is_connector"))
    return False


def _commit_rows(conn, m: dict, user, rows: list[dict], resolutions: dict | None, message: str) -> dict:
    _dependencies(conn, m, rows)
    resolutions = resolutions or {}
    conflicts = [c for c in (_conflict(conn, m, r, resolutions.get(str(r["guid"]))) for r in rows) if c]
    if conflicts:
        raise CommitConflict(conflicts)
    c = _new_commit(conn, m, user, "commit", message or "; ".join(r["label"] for r in rows[:3]) + ("..." if len(rows) > 3 else ""),
                    [r["author"] for r in rows])
    done = skipped = 0
    for r in rows:
        res = resolutions.get(str(r["guid"]))
        op, kind = r["op"], r["target_kind"]
        if res == "skip":
            _exec(conn, """UPDATE core.pending_changes SET status = 'rejected', note = 'Skipped at commit (it clashed with a later change)',
                           decided_by = :u, decided_at = now(), commit_id = :c WHERE id = :i""",
                  u=user.username.lower(), c=c["id"], i=r["id"])
            skipped += 1
            continue
        args = _resolved_args(r, res)
        target = _s(r["target"])
        before = _snap(conn, m, kind, target) if target else None
        if op in ("entity.delete", "relationship.delete") and (before is None or before["deleted"]):
            after = before
        else:
            sp = conn.begin_nested()
            try:
                _apply(conn, m, op, args, r["author"])
                sp.commit()
            except (EditError, repo.NotFound) as exc:
                sp.rollback()
                raise EditError(f"{r['label']}: {exc}", getattr(exc, "status", 409)) from exc
            after = _snap(conn, m, kind, target) if target else None
        _item(conn, c["id"], r["id"], r["author"], op, args, kind, target, r["label"], before, after)
        _exec(conn, "UPDATE core.pending_changes SET status = 'committed', commit_id = :c, decided_by = :u, decided_at = now() "
                    "WHERE id = :i", c=c["id"], u=user.username.lower(), i=r["id"])
        done += 1
    # data quality rules of severity error block the commit (phase 12, D239.8): checked on the entities it touched
    from . import quality
    touched = set()
    for r in rows:
        args = r["args"] if isinstance(r["args"], dict) else _json(r["args"]) or {}
        if r["target_kind"] == "entity" and _s(r["target"]):
            touched.add(_s(r["target"]))
        data = args.get("data") or {}
        for k in ("source", "target"):
            if repo._as_guid(data.get(k)):
                touched.add(str(repo._as_guid(data.get(k))))
    errors = quality.commit_errors(conn, m, touched)
    if errors:
        raise EditError("This commit breaks data quality rules that are errors, so nothing was committed. Fix these first "
                        "(or ask the Model Admin about the rule):\n" + "\n".join(f"• {e}" for e in errors[:20])
                        + ("\n..." if len(errors) > 20 else ""), 409)
    for sid in {r["change_set_id"] for r in rows}:
        _close_if_done(conn, sid)
    quality.queue_entities(str(m["id"]), touched)      # recalculated in the background a few seconds later (D245)
    return {"commit": str(c["guid"]), "number": c["number"], "committed": done, "skipped": skipped}


# ---------------------------------------------------------------- restoring a target (roll back of a commit)
def _restore(conn, m: dict, kind: str, target: str, before: dict | None, actor: str, sync_relationships: bool) -> None:
    mid = str(m["id"])
    if kind == "relationship":
        cur = snap_relationship(conn, m, target)
        if before is None or before["deleted"]:
            if cur and not cur["deleted"]:
                ct.delete_relationship(conn, mid, target)
            return
        if cur is None:
            raise EditError("The relationship is no longer in the model.", 409)
        _exec(conn, """UPDATE core.relationships r SET is_deleted = false, name = :n
                         FROM core.entities s, core.entities t
                        WHERE r.guid = CAST(:g AS uuid) AND s.id = r.source_entity_id AND t.id = r.target_entity_id
                          AND NOT s.is_deleted AND NOT t.is_deleted""", g=target, n=before.get("name") or "")
        return
    cur = snap_entity(conn, m, target)
    if before is None or before["deleted"]:
        if cur and not cur["deleted"]:
            ct.delete_entity(conn, mid, target)
        return
    if cur is None:
        raise EditError("The entity is no longer in the model.", 409)
    eid = _one(conn, "SELECT id, entity_type_id FROM core.entities WHERE guid = CAST(:g AS uuid)", g=target)
    if cur["deleted"]:
        _exec(conn, "UPDATE core.entities SET is_deleted = false WHERE id = :e", e=eid["id"])
        if before.get("_value_ids"):
            _exec(conn, "UPDATE core.attribute_values SET is_deleted = false WHERE id = ANY (:i)", i=list(before["_value_ids"]))
        sync_relationships = True
    parent = None
    if before.get("parent"):
        p = _one(conn, "SELECT id FROM core.entities WHERE guid = CAST(:g AS uuid) AND NOT is_deleted", g=before["parent"])
        parent = p["id"] if p else None
    _exec(conn, """UPDATE core.entities SET name = :n, description = :d, parent_entity_id = :p, status_code = :s,
                          tags = CAST(:tags AS text[]) WHERE id = :e""",
          n=before["name"], d=before.get("description") or "", p=parent, s=before.get("status") or "published",
          tags=list(before.get("tags") or []), e=eid["id"])
    now = snap_entity(conn, m, target)
    values = {c: None for c in now["values"] if c not in (before.get("values") or {})}
    values.update(before.get("values") or {})
    if values:
        ct._set_values(conn, m, eid["id"], eid["entity_type_id"], values=values)
    if sync_relationships:
        want = set(before.get("relationships") or [])
        have = set(now["relationships"])
        for g in want - have:
            _exec(conn, """UPDATE core.relationships r SET is_deleted = false FROM core.entities s, core.entities t
                            WHERE r.guid = CAST(:g AS uuid) AND s.id = r.source_entity_id AND t.id = r.target_entity_id
                              AND NOT s.is_deleted AND NOT t.is_deleted""", g=g)
        if not cur["deleted"]:
            for g in have - want:
                _exec(conn, "UPDATE core.relationships SET is_deleted = true WHERE guid = CAST(:g AS uuid)", g=g)


def roll_back_commit(conn, model: Any, user, commit_id: Any, item_ids: list | None = None, force: bool = False,
                     message: str = "") -> dict:
    """Undoes a committed commit, whole or the chosen items, as a new commit: each target goes back to how
    it was before the item. When a target changed since, the answer lists them (force to go ahead)."""
    m = _model(conn, model)
    if not may_commit(conn, user, m):
        raise EditError("Rolling back a commit needs the Committer, Model Sub Admin or Model Admin role on this model.", 403)
    g = repo._as_guid(commit_id)
    c = _one(conn, "SELECT * FROM core.commits WHERE guid = :g AND model_id = :m", g=str(g), m=m["_id"]) if g else None
    if not c:
        raise EditError("No such commit in this model.", 404)
    items = _rows(conn, "SELECT * FROM core.commit_items WHERE commit_id = :c AND rolled_back_by IS NULL ORDER BY id DESC", c=c["id"])
    if item_ids:
        want = {int(x) for x in item_ids}
        items = [i for i in items if i["id"] in want]
    if not items:
        raise EditError("Nothing left to roll back in this commit.", 409)
    changed = []
    for i in items:
        cur = _snap(conn, m, i["target_kind"], _s(i["target"])) if i["target"] else None
        after = _json(i["after"])
        if (cur is None) != (after is None) or _differences(after or {}, cur or {}):   # relationships of others may move
            changed.append({"item": i["id"], "label": i["label"],
                            "fields": [{"field": FIELD_NAMES.get(f, f[6:] if f.startswith("value:") else f), "code": f,
                                        "committed": a, "now": b} for f, a, b in _differences(after or {}, cur or {})]})
    if changed and not force:
        err = CommitConflict([{**x, "kind": "changed_since", "message": "Changed since this commit; rolling back puts it back "
                                                                       "as it was before the commit anyway."} for x in changed])
        raise err
    rc = _new_commit(conn, m, user, "rollback", message or f"Roll back of commit {c['number']}",
                     [i["author"] for i in items], rolls_back=c["id"])
    for i in items:
        target = _s(i["target"])
        before_now = _snap(conn, m, i["target_kind"], target)
        sp = conn.begin_nested()
        try:
            _restore(conn, m, i["target_kind"], target, _json(i["before"]), user.username,
                     i["op"] in ("entity.rollback", "rollback:entity.rollback"))
            sp.commit()
        except (EditError, repo.NotFound) as exc:
            sp.rollback()
            raise EditError(f"Rolling back '{i['label']}': {exc}", getattr(exc, "status", 409)) from exc
        _item(conn, rc["id"], None, i["author"], "rollback:" + i["op"].removeprefix("rollback:"), {"item": i["id"]},
              i["target_kind"], target, f"Roll back: {i['label']}", before_now, _snap(conn, m, i["target_kind"], target))
        _exec(conn, "UPDATE core.commit_items SET rolled_back_by = :r WHERE id = :i", r=rc["id"], i=i["id"])
    return {"commit": str(rc["guid"]), "number": rc["number"], "rolled_back": len(items)}


# ---------------------------------------------------------------- commit history (D151: mine, or everyone's)
def commits(conn, model: Any, user, person: str = "", limit: int = 200) -> dict:
    m = _model(conn, model)
    me = user.username.lower()
    everyone = sees_history(conn, user, m)
    who = (person or "").strip().lower()
    if who and who != me and not everyone:
        raise EditError("Seeing other people's commits needs the History Viewer or Model Admin role on this model (D151).", 403)
    rows = _rows(conn, """
        SELECT c.id AS _id, c.guid AS id, c.number, c.kind, c.message, c.committed_by, c.committed_at, c.authors,
               r.number AS rolls_back,
               (SELECT count(*) FROM core.commit_items i WHERE i.commit_id = c.id) AS items,
               (SELECT count(*) FROM core.commit_items i WHERE i.commit_id = c.id AND i.rolled_back_by IS NOT NULL) AS rolled_back
          FROM core.commits c LEFT JOIN core.commits r ON r.id = c.rolls_back
         WHERE c.model_id = :m
           AND (:all OR c.committed_by = :me OR :me = ANY (c.authors))
           AND (:who = '' OR c.committed_by = :who OR :who = ANY (c.authors))
         ORDER BY c.number DESC LIMIT :n""", m=m["_id"], all=everyone, me=me, who=who, n=max(1, min(int(limit or 200), 1000)))
    for r in rows:
        r.pop("_id")
    people = _rows(conn, """SELECT DISTINCT p AS person FROM core.commits c, unnest(c.authors || c.committed_by) p
                             WHERE c.model_id = :m ORDER BY 1""", m=m["_id"]) if everyone else []
    return {"commits": rows, "everyone": everyone, "people": [p["person"] for p in people], "may_commit": may_commit(conn, user, m)}


def commit_detail(conn, model: Any, user, commit_id: Any) -> dict:
    m = _model(conn, model)
    g = repo._as_guid(commit_id)
    c = _one(conn, """SELECT c.*, r.number AS rolls_back_number FROM core.commits c LEFT JOIN core.commits r ON r.id = c.rolls_back
                       WHERE c.guid = :g AND c.model_id = :m""", g=str(g), m=m["_id"]) if g else None
    if not c:
        raise EditError("No such commit in this model.", 404)
    me = user.username.lower()
    if not sees_history(conn, user, m) and c["committed_by"] != me and me not in (c["authors"] or []):
        raise EditError("Seeing other people's commits needs the History Viewer or Model Admin role on this model (D151).", 403)
    items = _rows(conn, """SELECT i.id, i.op, i.label, i.author, i.target, i.target_kind, i.before, i.after, rb.number AS rolled_back_by
                             FROM core.commit_items i LEFT JOIN core.commits rb ON rb.id = i.rolled_back_by
                            WHERE i.commit_id = :c ORDER BY i.id""", c=c["id"])
    for i in items:
        b, a = _json(i.pop("before")), _json(i.pop("after"))
        i["changes"] = [{"field": FIELD_NAMES.get(f, f[6:] if f.startswith("value:") else f), "before": x, "after": y}
                        for f, x, y in _differences(b or {}, a or {}) if f != "relationships" and (x or y)]
        st = a or b or {}
        i["entity"] = st.get("source") if st.get("kind") == "relationship" else _s(i["target"])   # the entity page to open
        i["entity_deleted"] = bool(st.get("deleted")) if st.get("kind") == "entity" else False
        if st.get("kind") == "relationship":
            rel = f"{st.get('source_name')} {st.get('verb') or st.get('relationship_type')} {st.get('target_name')}"
            i["changes"] = [x for x in i["changes"] if x["field"] not in ("deleted", "Deleted")]
            if (b is None or b.get("deleted")) and a is not None and not a.get("deleted"):
                i["changes"].insert(0, {"field": "Relationship", "before": None, "after": rel})
            elif a is None or (a.get("deleted") and not (b or {}).get("deleted")):
                i["changes"].insert(0, {"field": "Relationship", "before": rel, "after": None})
        elif any(x["field"] == "Deleted" for x in i["changes"]):   # deleted or restored: the values come and go with it
            i["changes"] = [x for x in i["changes"] if x["field"] in ("Deleted", "Name")]
        elif b is None and a is not None:
            i["changes"] = [x for x in i["changes"] if x["field"] not in ("Name", "deleted", "Deleted", "Display ID", "Status")]
            i["changes"].insert(0, {"field": "Created", "before": None, "after": a.get("name")})
        i["target"] = _s(i["target"])
    return {"id": str(c["guid"]), "number": c["number"], "kind": c["kind"], "message": c["message"], "committed_by": c["committed_by"],
            "committed_at": c["committed_at"], "authors": c["authors"], "rolls_back": c["rolls_back_number"], "items": items,
            "may_roll_back": may_commit(conn, user, m)}


def latest(conn, model: Any) -> dict:
    """The last commit of a model (live updates, E37): open pages compare it with the one they loaded."""
    m = _model(conn, model)
    c = _one(conn, """SELECT number, committed_by, committed_at, message FROM core.commits WHERE model_id = :m
                       ORDER BY number DESC LIMIT 1""", m=m["_id"])
    return {"number": c["number"] if c else 0, "committed_by": c["committed_by"] if c else None,
            "committed_at": c["committed_at"] if c else None, "message": c["message"] if c else ""}
