"""Merging a child model into its parent (phases 19 and 20, D359, D422 to D425).

One merge-to-parent wizard, in four steps:

1. **Send.** The child's Model Admin sends the child for merge into its parent, with a note. The changes are worked out
   then, three-way, against the child's **starting point** (a tag of kind 'start' taken when the child was made from
   its parent, and again whenever it is refreshed from it):

   * a field only the child changed is a change, pre-accepted;
   * a field only the parent changed is left alone (the parent's stands);
   * a field both changed, differently, is a **conflict** the reviewers decide;
   * entities and relationships the child added are added; those it removed (and the parent left as they were) are
     removed; a removal of something the parent changed since, or a change to something the parent removed, is a
     conflict;
   * entity types, relationship types and attributes the child's metamodel has and the parent's lacks are additions
     (pre-accepted; only a Model Admin of the parent decides them).

   A child without a starting point (made before 0.17.0, or moved under its parent later) has nothing to compare with:
   every difference is a conflict.

2. **Review.** The parent's Model Admins and Committers accept or reject each change (a rejection needs a reason). A
   conflict accepted takes the child's value; rejected keeps the parent's.

3. **Merge.** Everything accepted goes into the parent as one commit (the parent is tagged first), the metamodel
   additions as one new metamodel version. The **merge report** (accepted, rejected with reasons, anything that
   failed) is kept with the request and downloads as a Word document.

4. **Afterwards** the child's Model Admin chooses: **freeze** the child (final), or **refresh** it from the parent
   (all content: the child becomes what the parent is now, tagged first, with a new starting point) and carry on.

Dropped (D359): copies by scope, overlap warnings, pulling down without merging, partial merges. Rules are here, never in
the database (D248).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from . import commits as cm
from . import model_ops as mo
from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError

_rows = repo._rows


def _one(conn, sql: str, **p) -> dict | None:
    r = _rows(conn, sql, **p)
    return r[0] if r else None


def _bypass(conn, on: bool) -> None:
    """The child and its parent are read whole, whatever the person may see of the other model (as pushdown, D84)."""
    conn.execute(text("SELECT set_config('eax.rls_bypass', :v, true)"), {"v": "on" if on else ""})


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------- roles
def _roles(conn, user, m: dict) -> set[str]:
    if user is None or perms.SUPER_ADMIN in (user.roles or ()):
        return {perms.MODEL_ADMIN, perms.COMMITTER}
    return set(perms.model_roles(conn, user.username, m["id"]))


def is_child_admin(conn, user, child: dict) -> bool:
    return perms.MODEL_ADMIN in _roles(conn, user, child)


def is_reviewer(conn, user, parent: dict) -> bool:
    return bool(_roles(conn, user, parent) & perms.MODEL_PERMISSIONS["model.commit"])


def is_parent_admin(conn, user, parent: dict) -> bool:
    return perms.MODEL_ADMIN in _roles(conn, user, parent)


# ---------------------------------------------------------------- the starting point
def mark_start(conn, model: Any, actor: str, why: str = "") -> dict | None:
    """Tags a child as it is now as its starting point (kind 'start'): taken when a child is made from its parent and
    when it is refreshed from it. Never fails what called it."""
    from . import tags as tg
    m = repo.get_model(conn, model)
    if not m.get("parent_model_id"):
        return None
    name = f"Starting point {datetime.now():%Y-%m-%d %H:%M}"
    n, base = 1, name
    while _one(conn, "SELECT 1 AS x FROM core.model_tags WHERE model_id = :m AND lower(name) = lower(:n)", m=m["_id"], n=name):
        n += 1
        name = f"{base} ({n})"
    desc = why or f"What {m['name']} was when it was made from {m.get('parent_model_name') or 'its parent'}: merges compare with it."
    try:
        return tg._insert(conn, m, name, desc, "start", actor)
    except EditError:
        return None


def _start_tag(conn, child_id: int) -> dict | None:
    return _one(conn, """SELECT id, guid, name, created_at, snapshot FROM core.model_tags
                          WHERE model_id = :m AND kind = 'start' ORDER BY created_at DESC, id DESC LIMIT 1""", m=child_id)


# ---------------------------------------------------------------- working out the changes (three-way)
FIELDS = ("name", "description", "parent")


def _fields(st: dict) -> dict[str, Any]:
    """An entity state's comparable fields: name, description, parent and each value (codes in lower case)."""
    out = {"name": (st.get("name") or "").strip(), "description": (st.get("description") or "").strip() or None,
           "parent": st.get("parent") or None}
    for k, v in (st.get("values") or {}).items():
        out[f"value:{k}"] = v if v not in ("", None) else None
    return out


def _label(code: str, attr_names: dict[str, str]) -> str:
    if code.startswith("value:"):
        return attr_names.get(code[6:].lower(), code[6:])
    return {"name": "Name", "description": "Description", "parent": "Part of"}.get(code, code)


def plan(conn, child: dict, parent: dict) -> dict:
    """The changes merging the child into its parent would make, worked out three-way against the child's starting
    point. Read past row-level security (both models whole)."""
    from . import tags as tg
    _bypass(conn, True)
    try:
        start = _start_tag(conn, child["_id"])
        base = cm._json(start["snapshot"])["entities"] if start else None
        base_rels = cm._json(start["snapshot"])["relationships"] if start else None
        C = tg.snapshot(conn, child)
        P = tg.snapshot(conn, parent)
        cspec = mo.metamodel_spec(conn, str(child["id"]))
        pspec = mo.metamodel_spec(conn, str(parent["id"]))
    finally:
        _bypass(conn, False)
    ce, pe = C["entities"], P["entities"]
    attr_names = {a["code"].lower(): a.get("name") or a["code"] for a in (cspec.get("attributes") or [])}
    ref_attrs = {a["code"].lower() for a in (cspec.get("attributes") or []) if a.get("data_type") == "entity_ref"}
    p_by_name = {(e["type_code"].lower(), e["name"].strip().lower()): g for g, e in pe.items()}

    # each child entity's counterpart in the parent: its origin, else one of the same type and name
    to_parent: dict[str, str] = {}
    for g, e in {**(base or {}), **ce}.items():
        o = e.get("origin")
        if o and o in pe:
            to_parent[g] = o
        elif g in ce:
            hit = p_by_name.get((e["type_code"].lower(), e["name"].strip().lower()))
            if hit and hit not in to_parent.values():
                to_parent[g] = hit

    def ps(v: Any, code: str) -> Any:
        """A child-side value in the parent's terms: an entity (parent, reference) becomes its counterpart."""
        if v is None:
            return None
        if code == "parent" or (code.startswith("value:") and code[6:].lower() in ref_attrs):
            return to_parent.get(str(v), f"new:{v}")
        return v

    def show(v: Any, code: str, side: str = "child") -> Any:
        if v is None:
            return None
        if code == "parent" or (code.startswith("value:") and code[6:].lower() in ref_attrs):
            s = str(v)
            if s.startswith("new:"):
                s = s[4:]
                return (ce.get(s) or (base or {}).get(s) or {}).get("name", s)
            return (pe.get(s) or ce.get(s) or (base or {}).get(s) or {}).get("name", s)
        return v

    changes: list[dict] = []

    def add(**c):
        c.setdefault("conflict", False)
        c["id"] = c["id"][:200]
        changes.append(c)

    # entities the child has
    for g, e in ce.items():
        pg = to_parent.get(g)
        b = (base or {}).get(g)
        cf = {k: ps(v, k) for k, v in _fields(e).items()}
        if pg is None:
            if b is not None and b.get("origin"):          # the parent removed it since; the child kept it
                bf = {k: ps(v, k) for k, v in _fields(b).items()}
                if cf == bf:
                    continue                                 # unchanged in the child: the parent's removal stands
                add(id=f"add:{g}", kind="add", entity=g, entity_type=e["entity_type"], type_code=e["type_code"], name=e["name"],
                    conflict=True, why="removed from the parent since the child started; changed in the child")
            else:
                add(id=f"add:{g}", kind="add", entity=g, entity_type=e["entity_type"], type_code=e["type_code"], name=e["name"],
                    conflict=base is None, why="new in the child" if base is not None else "not in the parent (no starting point to tell why)")
            continue
        pf = {k: v for k, v in _fields(pe[pg]).items()}
        bf = {k: ps(v, k) for k, v in _fields(b).items()} if b is not None else None
        for code in sorted(set(cf) | set(pf)):
            c, p = cf.get(code), pf.get(code)
            if c == p:
                continue
            if bf is not None:
                bv = bf.get(code)
                if c == bv:
                    continue                                 # only the parent changed it: the parent's stands
                conflict = p != bv
            else:
                conflict = True
            if code == "name" and not c:
                continue
            add(id=f"set:{g}:{code}", kind="update", entity=g, parent_entity=pg, entity_type=e["entity_type"], type_code=e["type_code"],
                name=e["name"], code=code, field=_label(code, attr_names),
                base=show(bf.get(code), code) if bf is not None else None, child=show(c, code), parent=show(p, code),
                value=c, conflict=conflict,
                why=("changed in the child and in the parent" if conflict and bf is not None else
                     "differs (no starting point to tell who changed it)" if conflict else "changed in the child"))
    # entities the child removed
    for g, b in (base or {}).items():
        if g in ce:
            continue
        pg = to_parent.get(g)
        if not pg:
            continue                                         # gone from both
        bf = {k: ps(v, k) for k, v in _fields(b).items()}
        pf = _fields(pe[pg])
        changed = {k for k in set(bf) | set(pf) if bf.get(k) != pf.get(k)}
        add(id=f"del:{g}", kind="delete", entity=g, parent_entity=pg, entity_type=b["entity_type"], type_code=b["type_code"],
            name=pe[pg]["name"], conflict=bool(changed),
            why="removed in the child; changed in the parent since" if changed else "removed in the child")

    # relationships, in the parent's terms (type, source, target)
    def key(r: dict) -> tuple[str, str, str]:
        return (r["type_code"].lower(), to_parent.get(r["source"], f"new:{r['source']}"), to_parent.get(r["target"], f"new:{r['target']}"))
    p_rels = {(r["type_code"].lower(), r["source"], r["target"]): g for g, r in P["relationships"].items()}
    b_keys = {key(r) for r in (base_rels or {}).values()} if base_rels is not None else None
    c_keys = {}
    for g, r in C["relationships"].items():
        k = key(r)
        c_keys[k] = (g, r)
        if k in p_rels:
            continue
        if b_keys is not None and k in b_keys:
            continue                                         # the parent removed it since: its removal stands
        add(id=f"rel:{g}", kind="relate", relationship=g, type_code=r["type_code"], relationship_type=r["relationship_type"],
            source=r["source"], target=r["target"], source_name=r["source_name"], target_name=r["target_name"], rel_name=r.get("name") or "",
            name=f"{r['source_name']} {r.get('verb') or r['relationship_type']} {r['target_name']}",
            conflict=b_keys is None, why="new in the child" if b_keys is not None else "not in the parent (no starting point to tell why)")
    gone = {c["parent_entity"] for c in changes if c["kind"] == "delete"}
    for g, r in (base_rels or {}).items():
        k = key(r)
        if k in c_keys or k not in p_rels or k[1] in gone or k[2] in gone:
            continue                                         # (an entity removed takes its relationships with it)
        add(id=f"unrel:{g}", kind="unrelate", relationship=p_rels[k], type_code=r["type_code"], relationship_type=r["relationship_type"],
            source_name=r["source_name"], target_name=r["target_name"],
            name=f"{r['source_name']} {r.get('verb') or r['relationship_type']} {r['target_name']}", why="removed in the child")

    # the metamodel: what the child's has and the parent's lacks
    have_t = {t["code"].lower() for t in pspec.get("entity_types") or []}
    have_r = {r["code"].lower() for r in pspec.get("relationship_types") or []}
    have_a = {a["code"].lower() for a in pspec.get("attributes") or []}
    p_types = {t["code"].lower(): t for t in pspec.get("entity_types") or []}
    for t in cspec.get("entity_types") or []:
        if t["code"].lower() not in have_t:
            add(id=f"mm:type:{t['code']}", kind="metamodel", section="entity_types", code=t["code"], name=t.get("name") or t["code"],
                why="an entity type the parent's metamodel lacks")
        else:
            mine = {a["attribute"].lower() for a in p_types[t["code"].lower()].get("attributes") or []}
            for a in t.get("attributes") or []:
                if a["attribute"].lower() not in mine:
                    add(id=f"mm:attr:{t['code']}:{a['attribute']}", kind="metamodel", section="type_attributes", code=a["attribute"],
                        entity_type=t.get("name") or t["code"], type_code=t["code"],
                        name=f"{attr_names.get(a['attribute'].lower(), a['attribute'])} on {t.get('name') or t['code']}",
                        new_attribute=a["attribute"].lower() not in have_a, why="an attribute the parent's type lacks")
    for r in cspec.get("relationship_types") or []:
        if r["code"].lower() not in have_r:
            add(id=f"mm:rel:{r['code']}", kind="metamodel", section="relationship_types", code=r["code"], name=r.get("name") or r["code"],
                why="a relationship type the parent's metamodel lacks")

    order = {"metamodel": 0, "add": 1, "update": 2, "delete": 3, "relate": 4, "unrelate": 5}
    changes.sort(key=lambda c: (order[c["kind"]], not c["conflict"], c.get("entity_type") or "", c.get("name") or "", c.get("field") or ""))
    counts = {k: sum(1 for c in changes if c["kind"] == k) for k in order}
    counts["conflicts"] = sum(1 for c in changes if c["conflict"])
    counts["total"] = len(changes)
    return {"child": {"id": str(child["id"]), "name": child["name"]}, "parent": {"id": str(parent["id"]), "name": parent["name"]},
            "base": {"id": str(start["guid"]), "name": start["name"], "at": str(start["created_at"])} if start else None,
            "changes": changes, "counts": counts, "spec": cspec}


# ---------------------------------------------------------------- requests
def _out(conn, r: dict, user=None, full: bool = False) -> dict:
    p = cm._json(r["plan"]) or {}
    d = cm._json(r["decisions"]) or {}
    changes = p.get("changes") or []
    undecided = [c["id"] for c in changes if c.get("conflict") and c["id"] not in d]
    rejected = sum(1 for c in changes if (d.get(c["id"]) or {}).get("accept") is False)
    out = {"id": str(r["guid"]), "number": r["number"], "status": r["status"], "after": r["after"], "note": r["note"],
           "child": p.get("child"), "parent": p.get("parent"), "base": p.get("base"), "counts": p.get("counts"),
           "undecided": len(undecided), "rejected": rejected, "decided": len(d),
           "sent_by": r["sent_by"], "sent_at": r["sent_at"], "merged_by": r["merged_by"], "merged_at": r["merged_at"],
           "closed_by": r["closed_by"], "closed_at": r["closed_at"]}
    if user is not None:
        child = _model_row(conn, r["child_id"])
        parent = _model_row(conn, r["parent_id"])
        out["you"] = {"child_admin": is_child_admin(conn, user, child), "reviewer": is_reviewer(conn, user, parent),
                      "parent_admin": is_parent_admin(conn, user, parent)}
    if full:
        out["changes"] = [{k: v for k, v in c.items() if k != "value"} | {"decision": d.get(c["id"])} for c in changes]
        out["report"] = cm._json(r["report"]) if r["report"] else None
    return out


def _model_row(conn, mid: int) -> dict:
    _bypass(conn, True)
    try:
        g = _one(conn, "SELECT guid::text AS g FROM core.models WHERE id = :i", i=mid)["g"]
        return repo.get_model(conn, g)
    finally:
        _bypass(conn, False)


def _request(conn, rid: Any) -> dict:
    g = repo._as_guid(rid)
    r = _one(conn, "SELECT * FROM core.merge_requests WHERE guid = :g", g=str(g)) if g else None
    if not r:
        raise EditError("No such merge request.", 404)
    return r


def _may_see(conn, user, r: dict) -> None:
    if user is None or perms.SUPER_ADMIN in (user.roles or ()):
        return
    for mid in (r["child_id"], r["parent_id"]):
        if perms.model_roles(conn, user.username, _model_row(conn, mid)["id"]):
            return
    raise EditError("This merge request is for the people of the child or the parent model.", 403)


def listing(conn, model: Any, user) -> dict:
    """A model's merge requests: those it sent (as a child) and those sent to it (as a parent)."""
    m = repo.get_model(conn, model)
    rows = _rows(conn, """SELECT * FROM core.merge_requests WHERE child_id = :m OR parent_id = :m
                           ORDER BY sent_at DESC, id DESC LIMIT 200""", m=m["_id"])
    open_sent = next((r for r in rows if r["child_id"] == m["_id"] and r["status"] == "sent"), None)
    return {"model": {"id": str(m["id"]), "name": m["name"]},
            "parent": {"id": str(m["parent_model_id"]), "name": m.get("parent_model_name")} if m.get("parent_model_id") else None,
            "sent": [_out(conn, r) for r in rows if r["child_id"] == m["_id"]],
            "received": [_out(conn, r) for r in rows if r["parent_id"] == m["_id"]],
            "open": str(open_sent["guid"]) if open_sent else None}


def waiting_for(conn, user) -> list[dict]:
    """Requests waiting for this person: to review (a Committer or Model Admin of the parent) or to choose freeze or
    refresh (a Model Admin of the child)."""
    rows = _rows(conn, "SELECT * FROM core.merge_requests WHERE status IN ('sent', 'merged') ORDER BY sent_at")
    out = []
    for r in rows:
        if r["status"] == "sent" and is_reviewer(conn, user, _model_row(conn, r["parent_id"])):
            out.append({**_out(conn, r), "waiting": "review"})
        elif r["status"] == "merged" and is_child_admin(conn, user, _model_row(conn, r["child_id"])):
            out.append({**_out(conn, r), "waiting": "choose freeze or refresh"})
    return out


def get(conn, rid: Any, user) -> dict:
    r = _request(conn, rid)
    _may_see(conn, user, r)
    return _out(conn, r, user, full=True)


def _check_child(conn, child: dict, user) -> None:
    if not child.get("parent_model_id"):
        raise EditError(f"{child['name']} has no parent model to merge into.", 409)
    if child.get("frozen_at"):
        raise EditError(f"{child['name']} is frozen: it was merged already, or is final.", 409)
    if not is_child_admin(conn, user, child):
        raise EditError(f"Sending {child['name']} for merge needs the Model Admin role on it.", 403)


def preview(conn, model: Any, user) -> dict:
    """What sending the child would ask the parent's reviewers: the changes found, nothing kept."""
    child = repo.get_model(conn, model)
    parent = _parent(conn, child)
    _check_child(conn, child, user)
    p = plan(conn, child, parent)
    return {k: v for k, v in p.items() if k != "spec"}


def _parent(conn, child: dict) -> dict:
    if not child.get("parent_model_id"):
        raise EditError(f"{child['name']} has no parent model to merge into.", 409)
    _bypass(conn, True)
    try:
        return repo.get_model(conn, str(child["parent_model_id"]))
    finally:
        _bypass(conn, False)


def send(conn, model: Any, user, note: str = "") -> dict:
    """The child's Model Admin sends the child for merge: the changes are worked out now and kept with the request; the
    parent's Model Admins and Committers are told."""
    from . import notify
    child = repo.get_model(conn, model)
    parent = _parent(conn, child)
    _check_child(conn, child, user)
    if _one(conn, "SELECT 1 AS x FROM core.merge_requests WHERE child_id = :c AND status IN ('sent', 'merged')", c=child["_id"]):
        raise EditError(f"{child['name']} has a merge request open already: withdraw it, or finish it, first.", 409)
    if parent.get("frozen_at"):
        raise EditError(f"{parent['name']} is frozen: nothing can be merged into it.", 409)
    p = plan(conn, child, parent)
    if not p["changes"]:
        raise EditError(f"{child['name']} has nothing to merge: nothing differs from {parent['name']} that the child changed.", 409)
    start = _start_tag(conn, child["_id"])
    num = (_one(conn, "SELECT coalesce(max(number), 0) + 1 AS n FROM core.merge_requests WHERE parent_id = :p", p=parent["_id"]) or {"n": 1})["n"]
    row = _one(conn, """INSERT INTO core.merge_requests (number, child_id, parent_id, note, base_tag_id, plan, sent_by)
                        VALUES (:n, :c, :p, :note, :b, CAST(:plan AS jsonb), :by) RETURNING *""",
               n=num, c=child["_id"], p=parent["_id"], note=(note or "").strip()[:2000], b=start["id"] if start else None,
               plan=json.dumps(p, default=str), by=user.username.lower())
    who = sorted({r["u"] for r in _rows(conn, """SELECT lower(username) AS u FROM core.model_users
                                                  WHERE model_id = :m AND role = ANY (CAST(:r AS text[]))""",
                                        m=parent["_id"], r=sorted(perms.MODEL_PERMISSIONS["model.commit"]))})
    if who:
        notify.create(conn, kind="merge.requested", category="request", title=f"{child['name']} was sent for merge into {parent['name']}",
                      actor=user.username, body=(note or "")[:500], link=f"#/merge-requests/{row['guid']}", recipients=who,
                      needs_action=True, model_id=parent["_id"])
    return _out(conn, row, user)


def withdraw(conn, rid: Any, user, note: str = "") -> dict:
    r = _request(conn, rid)
    child = _model_row(conn, r["child_id"])
    if r["status"] != "sent":
        raise EditError(f"Only a request waiting for review is withdrawn; this one is {r['status']}.", 409)
    if r["sent_by"] != user.username.lower() and not is_child_admin(conn, user, child):
        raise EditError("The person who sent it, or a Model Admin of the child, withdraws it.", 403)
    row = _one(conn, """UPDATE core.merge_requests SET status = 'withdrawn', closed_by = :u, closed_at = now(),
                                note = CASE WHEN :n = '' THEN note ELSE note || E'\n\nWithdrawn: ' || :n END
                         WHERE id = :i RETURNING *""", u=user.username.lower(), n=(note or "").strip()[:1000], i=r["id"])
    return _out(conn, row, user)


def decide(conn, rid: Any, user, decisions: dict) -> dict:
    """Reviewers' decisions, change by change: {change id: {"accept": bool, "reason": text}}; {"accept": null} takes a
    decision back. A rejection needs a reason; metamodel additions are decided by a Model Admin of the parent."""
    r = _request(conn, rid)
    if r["status"] != "sent":
        raise EditError(f"This request is {r['status']}: its decisions are final.", 409)
    parent = _model_row(conn, r["parent_id"])
    if not is_reviewer(conn, user, parent):
        raise EditError(f"Reviewing a merge into {parent['name']} needs the Committer, Model Sub Admin or Model Admin role on it.", 403)
    admin = is_parent_admin(conn, user, parent)
    changes = {c["id"]: c for c in (cm._json(r["plan"]) or {}).get("changes") or []}
    have = cm._json(r["decisions"]) or {}
    for cid, d in (decisions or {}).items():
        c = changes.get(cid)
        if not c:
            raise EditError(f"No change {cid!r} in this request.", 404)
        if c["kind"] == "metamodel" and not admin:
            raise EditError(f"Adding {c['name']} to the metamodel of {parent['name']} is decided by its Model Admin.", 403)
        acc = (d or {}).get("accept")
        if acc is None:
            have.pop(cid, None)
            continue
        reason = ((d or {}).get("reason") or "").strip()[:500]
        if acc is False and not reason:
            raise EditError(f"Say why {c.get('name') or 'this change'}{' (' + c['field'] + ')' if c.get('field') else ''} is rejected.")
        have[cid] = {"accept": bool(acc), "reason": reason, "by": user.username.lower(), "at": _now()}
    row = _one(conn, "UPDATE core.merge_requests SET decisions = CAST(:d AS jsonb) WHERE id = :i RETURNING *",
               d=json.dumps(have), i=r["id"])
    return _out(conn, row, user, full=True)


def _accepted(c: dict, d: dict) -> bool:
    x = d.get(c["id"])
    if x is None:
        return not c.get("conflict")          # pre-accepted unless it is a conflict
    return bool(x.get("accept"))


def merge(conn, rid: Any, user) -> dict:
    """Puts everything accepted into the parent: the metamodel additions (one version), then the content as one commit
    (the parent tagged first). Keeps the merge report and tells the child's Model Admins to choose freeze or refresh."""
    from . import merge as mg
    from . import model_wizards as mw
    from . import notify
    r = _request(conn, rid)
    if r["status"] != "sent":
        raise EditError(f"This request is {r['status']} already.", 409)
    parent = _model_row(conn, r["parent_id"])
    child = _model_row(conn, r["child_id"])
    if not is_reviewer(conn, user, parent):
        raise EditError(f"Merging into {parent['name']} needs the Committer, Model Sub Admin or Model Admin role on it.", 403)
    why = mg.blocked(conn, parent, _AsAdmin(user)) if not parent.get("frozen_at") else f"{parent['name']} is frozen."
    if why and "Model Admin role" not in why:
        raise EditError(why, 409)
    p = cm._json(r["plan"])
    d = cm._json(r["decisions"]) or {}
    changes = p["changes"]
    undecided = [c for c in changes if c.get("conflict") and c["id"] not in d]
    if undecided:
        raise EditError(f"Decide every conflict first: {len(undecided)} left.", 409)
    acc = [c for c in changes if _accepted(c, d)]
    if any(c["kind"] == "metamodel" for c in acc) and not is_parent_admin(conn, user, parent):
        raise EditError(f"The merge adds to the metamodel of {parent['name']}: its Model Admin merges it.", 403)
    tag = mw.tag_first(conn, str(parent["id"]), user, f"merging {child['name']}")
    version = _add_metamodel(conn, parent, p["spec"], [c for c in acc if c["kind"] == "metamodel"], user)

    # content, in the parent's terms
    known_types = {x["code"].lower() for x in _rows(conn, "SELECT code FROM core.entity_types WHERE model_id = :m AND NOT is_deleted",
                                                     m=parent["_id"])}
    snap_child = _child_states(conn, child, [c["entity"] for c in acc if c["kind"] == "add"])
    to_parent = {c["entity"]: c["parent_entity"] for c in changes if c.get("parent_entity") and c.get("entity")}
    new_guid: dict[str, str] = {}
    left_out: list[dict] = []
    for c in acc:
        if c["kind"] == "add":
            if c["type_code"].lower() not in known_types:
                left_out.append({"change": c["id"], "what": c["name"], "why": f"its type {c['entity_type']} is not in the parent's metamodel"})
                continue
            new_guid[c["entity"]] = str(uuid.uuid4())

    def mapped(v: Any) -> Any:
        if v is None:
            return ""
        s = str(v)
        if s.startswith("new:"):
            return new_guid.get(s[4:], "")
        return s

    def mapped_child(v: Any) -> Any:          # a child guid (from the child's own state)
        if v in (None, ""):
            return ""
        return new_guid.get(str(v)) or to_parent.get(str(v)) or ""

    items: list[tuple[str, dict]] = []
    later: list[tuple[str, dict]] = []
    updates: dict[str, dict] = {}
    ref_attrs = {a["code"].lower() for a in (p["spec"].get("attributes") or []) if a.get("data_type") == "entity_ref"}
    for c in acc:
        if c["kind"] == "add" and c["entity"] in new_guid:
            st = snap_child.get(c["entity"]) or {}
            vals = {k: (mapped_child(v) if k.lower() in ref_attrs else v) for k, v in (st.get("values") or {}).items() if v not in (None, "")}
            data = {"guid": new_guid[c["entity"]], "entity_type": c["type_code"], "name": st.get("name") or c["name"],
                    "description": st.get("description") or "", "values": {k: v for k, v in vals.items() if v != ""}}
            items.append(("entity.create", {"data": data}))
            if st.get("parent"):
                pg = mapped_child(st["parent"])
                if pg:
                    later.append((new_guid[c["entity"]], {"parent": pg}))
        elif c["kind"] == "update":
            u = updates.setdefault(c["parent_entity"], {})
            code = c["code"]
            if code in ("name", "description"):
                u[code] = c["value"] or ""
            elif code == "parent":
                u["parent"] = mapped(c["value"])
            else:
                v = c["value"]
                u.setdefault("values", {})[code[6:]] = mapped(v) if code[6:].lower() in ref_attrs else ("" if v is None else v)
    items += [("entity.update", {"entity": g, "data": dd}) for g, dd in updates.items()]
    items += [("entity.update", {"entity": g, "data": dd}) for g, dd in later]
    for c in acc:
        if c["kind"] == "delete":
            items.append(("entity.delete", {"entity": c["parent_entity"]}))
        elif c["kind"] == "relate":
            s, t = mapped_child(c["source"]), mapped_child(c["target"])
            if not s or not t:
                left_out.append({"change": c["id"], "what": c["name"], "why": "one of its ends was not taken"})
                continue
            items.append(("relationship.create", {"data": {"relationship_type": c["type_code"], "source": s, "target": t,
                                                           "name": c.get("rel_name") or "", "allow_outside": True}}))
        elif c["kind"] == "unrelate":
            items.append(("relationship.delete", {"relationship": c["relationship"]}))
    results = cm.record_many(conn, parent["id"], user.username, items) if items else []
    failed = [{"change": op, "what": (a.get("data") or {}).get("name") or a.get("entity") or a.get("relationship"), "error": x["error"]}
              for (op, a), x in zip(items, results, strict=True) if not x["ok"]]
    ids = [x["kept"]["change"] for x in results if x.get("ok") and x.get("kept")]
    done = cm.commit(conn, parent["id"], _AsAdmin(user), None, ids, None,
                     f"Merge of {child['name']} (merge request {r['number']})") if ids else None
    # the child's new entities now have a counterpart in the parent: later merges and refreshes find it
    made = {cg: pg for cg, pg in new_guid.items()
            if _one(conn, "SELECT 1 AS x FROM core.entities WHERE guid = CAST(:g AS uuid) AND NOT is_deleted", g=pg)}
    if made:
        _bypass(conn, True)
        try:
            for cg, pg in made.items():
                conn.execute(text("UPDATE core.entities SET origin_guid = CAST(:p AS uuid) WHERE guid = CAST(:c AS uuid) AND model_id = :m"),
                             {"p": pg, "c": cg, "m": child["_id"]})
        finally:
            _bypass(conn, False)
    rej = [c for c in changes if not _accepted(c, d)]
    report = {"child": p["child"], "parent": p["parent"], "number": r["number"], "sent_by": r["sent_by"], "sent_at": str(r["sent_at"]),
              "merged_by": user.username.lower(), "merged_at": _now(), "base": p.get("base"),
              "tag": {"id": str(tag.get("id") or tag.get("guid")), "name": tag["name"]} if tag else None,
              "commit": done["number"] if done else None, "metamodel_version": version,
              "accepted": [_line(c, d) for c in acc], "rejected": [_line(c, d) for c in rej],
              "failed": failed[:200], "left_out": left_out}
    row = _one(conn, """UPDATE core.merge_requests SET status = 'merged', merged_by = :u, merged_at = now(), report = CAST(:rep AS jsonb)
                         WHERE id = :i RETURNING *""", u=user.username.lower(), rep=json.dumps(report, default=str), i=r["id"])
    admins = sorted({r["sent_by"]} | {x["u"] for x in _rows(conn, """SELECT lower(username) AS u FROM core.model_users
                                                                   WHERE model_id = :m AND role = :r""", m=child["_id"], r=perms.MODEL_ADMIN)})
    notify.create(conn, kind="merge.merged", category="request", title=f"{child['name']} was merged into {parent['name']}: freeze it or refresh it",
                  actor=user.username, body=f"{len(acc)} changes accepted, {len(rej)} rejected.", link=f"#/merge-requests/{row['guid']}",
                  recipients=admins, needs_action=True, model_id=child["_id"])
    out = _out(conn, row, user, full=True)
    out["message"] = (f"Merged into {parent['name']}" + (f" as commit {done['number']}" if done else "") +
                      f": {len(acc)} changes accepted, {len(rej)} rejected" + (f", {len(failed)} failed" if failed else "") +
                      f". The report is kept with the request. {child['name']}'s Model Admin now chooses: freeze it, or refresh it.")
    return out


class _AsAdmin:
    """The reviewer, for the merge's own checks: the right to review was checked here already."""

    def __init__(self, user):
        self.username = user.username
        self.roles = tuple(user.roles or ()) + (perms.SUPER_ADMIN,)


def _line(c: dict, d: dict) -> dict:
    x = d.get(c["id"]) or {}
    return {"id": c["id"], "kind": c["kind"], "entity_type": c.get("entity_type") or c.get("relationship_type") or c.get("section"),
            "name": c.get("name"), "field": c.get("field"), "child": c.get("child"), "parent": c.get("parent"),
            "conflict": bool(c.get("conflict")), "reason": x.get("reason") or "", "by": x.get("by") or ("pre-accepted" if not x else ""),
            "why": c.get("why")}


def _child_states(conn, child: dict, guids: list[str]) -> dict[str, dict]:
    if not guids:
        return {}
    _bypass(conn, True)
    try:
        return {g: cm.snap_entity(conn, child, g) or {} for g in guids}
    finally:
        _bypass(conn, False)


def _add_metamodel(conn, parent: dict, spec: dict, items: list[dict], user) -> int | None:
    """The accepted metamodel additions, as one new metamodel version (the merge module's own way of adding)."""
    from . import merge as mg
    if not items:
        return None
    gaps = {"entity_types": [{"code": c["code"], "name": c["name"]} for c in items if c["section"] == "entity_types"],
            "relationship_types": [{"code": c["code"], "name": c["name"]} for c in items if c["section"] == "relationship_types"],
            "attributes": [], "type_attributes": []}
    want_attrs = {(c["type_code"].lower(), c["code"].lower()) for c in items if c["section"] == "type_attributes"}
    types = {g["code"].lower() for g in gaps["entity_types"]}
    trimmed = json.loads(json.dumps(spec, default=str))
    for t in trimmed.get("entity_types") or []:
        if t["code"].lower() not in types:
            t["attributes"] = [a for a in t.get("attributes") or [] if (t["code"].lower(), a["attribute"].lower()) in want_attrs]
    return mg._add_metamodel(conn, parent, trimmed, gaps, _AsAdmin(user))


def finish(conn, rid: Any, user, choice: str, note: str = "") -> dict:
    """After the merge the child's Model Admin chooses: freeze the child (final), or refresh it from the parent and carry on."""
    from . import model_wizards as mw
    r = _request(conn, rid)
    if r["status"] != "merged":
        raise EditError("Freeze or refresh comes after the merge." if r["status"] == "sent" else f"This request is {r['status']}.", 409)
    child = _model_row(conn, r["child_id"])
    if not is_child_admin(conn, user, child):
        raise EditError(f"Freezing or refreshing {child['name']} needs the Model Admin role on it.", 403)
    if choice == "freeze":
        mw.freeze(conn, str(child["id"]), user, note or f"Merged into its parent (merge request {r['number']}).")
        result = {"message": f"{child['name']} is frozen: read only for good. It can still be copied, compared and reported on."}
    elif choice == "refresh":
        result = refresh(conn, child, user)
    else:
        raise EditError("Choose freeze or refresh.")
    row = _one(conn, """UPDATE core.merge_requests SET status = 'closed', after = :a, closed_by = :u, closed_at = now()
                         WHERE id = :i RETURNING *""", a="frozen" if choice == "freeze" else "refreshed", u=user.username.lower(), i=r["id"])
    return {**_out(conn, row, user, full=True), **result}


def refresh(conn, child: dict, user) -> dict:
    """The child becomes what its parent is now (all content), as one commit in the child (tagged first), and a new
    starting point is taken. Metamodel parts the parent has and the child lacks are added; nothing of the child's
    metamodel is taken away (D289)."""
    from . import model_wizards as mw
    from . import tags as tg
    parent = _parent(conn, child)
    tag = mw.tag_first(conn, str(child["id"]), user, f"refreshing from {parent['name']}")
    _bypass(conn, True)
    try:
        P = tg.snapshot(conn, parent)
        C = tg.snapshot(conn, child)
        pspec = mo.metamodel_spec(conn, str(parent["id"]))
    finally:
        _bypass(conn, False)
    mo.apply_spec(conn, child["_id"], pspec, "merge")
    ref_attrs = {a["code"].lower() for a in (pspec.get("attributes") or []) if a.get("data_type") == "entity_ref"}
    by_origin = {e["origin"]: g for g, e in C["entities"].items() if e.get("origin")}
    to_child: dict[str, str] = {}
    created: dict[str, str] = {}
    for pg in P["entities"]:
        to_child[pg] = by_origin.get(pg) or created.setdefault(pg, str(uuid.uuid4()))
    items: list[tuple[str, dict]] = []
    later: list[tuple[str, dict]] = []
    for pg, e in P["entities"].items():
        cg = to_child[pg]
        vals = {k: (to_child.get(str(v), "") if k.lower() in ref_attrs else v) for k, v in (e.get("values") or {}).items()}
        par = to_child.get(e["parent"] or "", "") if e.get("parent") else ""
        if pg in created:
            items.append(("entity.create", {"data": {"guid": cg, "entity_type": e["type_code"], "name": e["name"],
                                                     "description": e["description"] or "", "values": {k: v for k, v in vals.items() if v}}}))
            if par:
                later.append((cg, {"parent": par}))
            continue
        mine = C["entities"][cg]
        data: dict[str, Any] = {}
        if mine["name"] != e["name"]:
            data["name"] = e["name"]
        if (mine["description"] or "") != (e["description"] or ""):
            data["description"] = e["description"] or ""
        if (mine.get("parent") or "") != par:
            data["parent"] = par
        v2 = {k: v for k, v in vals.items() if (mine.get("values") or {}).get(k) != v}
        v2.update({k: "" for k in (mine.get("values") or {}) if k not in vals})
        if v2:
            data["values"] = v2
        if data:
            later.append((cg, data))
    keep = set(to_child.values())
    items += [("entity.update", {"entity": g, "data": dd}) for g, dd in later]
    items += [("entity.delete", {"entity": g}) for g in C["entities"] if g not in keep]
    c_keys = {(r["type_code"].lower(), r["source"], r["target"]): g for g, r in C["relationships"].items()}
    p_keys = set()
    for r in P["relationships"].values():
        k = (r["type_code"].lower(), to_child.get(r["source"], ""), to_child.get(r["target"], ""))
        p_keys.add(k)
        if k not in c_keys and k[1] and k[2]:
            items.append(("relationship.create", {"data": {"relationship_type": r["type_code"], "source": k[1], "target": k[2],
                                                           "name": r.get("name") or "", "allow_outside": True}}))
    items += [("relationship.delete", {"relationship": g}) for k, g in c_keys.items() if k not in p_keys
              and k[1] in keep and k[2] in keep]
    results = cm.record_many(conn, child["id"], user.username, items) if items else []
    failed = [x["error"] for x in results if not x["ok"]]
    ids = [x["kept"]["change"] for x in results if x.get("ok") and x.get("kept")]
    done = cm.commit(conn, child["id"], _AsAdmin(user), None, ids, None, f"Refreshed from {parent['name']}") if ids else None
    if created:
        for pg, cg in created.items():
            conn.execute(text("UPDATE core.entities SET origin_guid = CAST(:p AS uuid) WHERE guid = CAST(:c AS uuid) AND model_id = :m"),
                         {"p": pg, "c": cg, "m": child["_id"]})
    start = mark_start(conn, str(child["id"]), user.username.lower(), f"{child['name']} refreshed from {parent['name']}: later merges compare with it.")
    return {"message": f"{child['name']} now holds what {parent['name']} holds" + (f" (commit {done['number']})" if done else "") +
                       (f"; {len(failed)} changes failed" if failed else "") + f". It was tagged first as {tag['name']}; carry on working in it.",
            "refresh": {"tag": tag["name"] if tag else None, "commit": done["number"] if done else None, "failed": failed[:20],
                        "start": start["name"] if start else None}}


# ---------------------------------------------------------------- the merge report as a Word document
def report_docx(conn, rid: Any, user) -> tuple[bytes, str]:
    from .gaps import _p, _table, docx_from
    r = _request(conn, rid)
    _may_see(conn, user, r)
    rep = cm._json(r["report"]) if r["report"] else None
    if not rep:
        raise EditError("The report is made when the request is merged.", 409)
    body = [_p(f"Merge report: {rep['child']['name']} into {rep['parent']['name']}", "Title"),
            _table([["", ""], ["Merge request", str(rep["number"])], ["Sent by", f"{rep['sent_by']}, {str(rep['sent_at'])[:16]}"],
                    ["Merged by", f"{rep['merged_by']}, {str(rep['merged_at'])[:16]}"],
                    ["Compared with", rep["base"]["name"] if rep.get("base") else "no starting point: every difference was decided"],
                    ["Commit in the parent", str(rep.get("commit") or "none")],
                    ["Tag taken first", (rep.get("tag") or {}).get("name") or ""],
                    ["Accepted", str(len(rep["accepted"]))], ["Rejected", str(len(rep["rejected"]))],
                    ["Failed", str(len(rep.get("failed") or []) + len(rep.get("left_out") or []))]])]

    def rows(lines, last):
        return [["Change", "Type", "Item", "Field", "Child", "Parent", last]] + [
            [{"add": "Added", "update": "Changed", "delete": "Removed", "relate": "Related", "unrelate": "Unrelated",
              "metamodel": "Metamodel"}.get(x["kind"], x["kind"]), x.get("entity_type") or "", x.get("name") or "", x.get("field") or "",
             str(x.get("child") if x.get("child") is not None else ""), str(x.get("parent") if x.get("parent") is not None else ""),
             x["reason"] if last == "Reason" else (("conflict, " if x["conflict"] else "") + (x.get("by") or ""))] for x in lines]
    body.append(_p("Accepted", "Heading1"))
    body.append(_table(rows(rep["accepted"], "Decided")) if rep["accepted"] else _p("None."))
    body.append(_p("Rejected, with the reasons", "Heading1"))
    body.append(_table(rows(rep["rejected"], "Reason")) if rep["rejected"] else _p("None."))
    if rep.get("failed") or rep.get("left_out"):
        body.append(_p("Not applied", "Heading1"))
        body.append(_table([["Change", "What", "Why"]] + [[f["change"], str(f.get("what") or ""), f.get("error") or ""] for f in rep.get("failed") or []]
                           + [[f["change"], str(f.get("what") or ""), f["why"]] for f in rep.get("left_out") or []]))
    name = f"Merge report {rep['child']['name']} into {rep['parent']['name']}.docx".replace("/", "-")
    return docx_from(body), name
