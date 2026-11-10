"""Model wizards (build phase 13.0.4, D283): the rules the wizards add to what the model screens already do.

The 20 wizards (the web shows each as a few steps with a preview; the slow ones run as background tasks, D273):

    1-3   copy a model: with the parent-child link, without it, or from a library model    model_ops.create_model
    4, 6  merge a model into its parent, choosing what goes in; freeze it after or not      merge (exclude) + freeze
    5     propagate the parent's changes into a child, choosing what goes in                 merge, parent into child
    15    pull a library model's newer content into a model built from it                   merge, library into model
    7     freeze a model: read only for good (a Super Admin unfreezes)                         freeze / unfreeze
    8     promote a model to the library                                                    model_ops.promote
    9     upgrade a model to another framework (e.g. ArchiMate 5)                           model_ops.framework_move
    10/11 lock and unlock (temporary)                                                      metamodel_edit.set_lock / clear_lock
    12    tag first: every risky wizard tags the model before it changes it                  tag_first
    13    detach a child from its parent, or move it under another project model             detach / reparent
    14    split a model: part of it into a new child or a separate model (copied or moved)   split
    16    restore a model from a tag (or a backup)                                          tags.restore_tag, backups
    17    archive, bring back, delete with a backup first                                   model_ops.set_lifecycle / delete_model
    18    extend the metamodel with parts of another model's metamodel                       extend_metamodel
    19    find duplicate entities in a model and merge them into one                         duplicates / merge_duplicates
    20    hand a model over: its Model Admins                                                hand_over

Rules are here, never in the database (D248); the database still refuses what the person may not do.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError

_rows = repo._rows


def _one(conn, sql: str, **p) -> dict | None:
    r = _rows(conn, sql, **p)
    return r[0] if r else None


def _admin(conn, user, m: dict, what: str) -> None:
    if perms.SUPER_ADMIN in (user.roles or ()):
        return
    if perms.MODEL_ADMIN not in perms.model_roles(conn, user.username, m["id"]):
        raise EditError(f"{what} needs the Model Admin role on {m['name']}.", 403)


# ---------------------------------------------------------------- 12: tag first
def tag_first(conn, model: Any, user, why: str) -> dict:
    """Tags the model as it is now before a wizard changes it, so it can be restored."""
    from datetime import datetime

    from . import tags as tg
    m = repo.get_model(conn, model)
    name = f"Before {why} {datetime.now():%Y-%m-%d %H:%M}"[:120]
    n, base = 1, name
    while _one(conn, "SELECT 1 AS x FROM core.model_tags WHERE model_id = :m AND lower(name) = lower(:n)", m=m["_id"], n=name):
        n += 1
        name = f"{base} ({n})"
    return tg.create_tag(conn, str(m["id"]), user, name, f"Taken by the model wizard before {why}.")


# ---------------------------------------------------------------- 7: freeze (final) and unfreeze (Super Admins)
def freeze(conn, model: Any, user, note: str = "") -> dict:
    m = repo.get_model(conn, model)
    _admin(conn, user, m, "Freezing a model")
    if m.get("frozen_at"):
        raise EditError(f"{m['name']} is frozen already.", 409)
    if m["kind"] != "project":
        raise EditError("Only a project model is frozen (root and library models are read only already).", 409)
    conn.execute(text("SELECT set_config('eax.actor', :a, true)"), {"a": user.username})
    conn.execute(text("""UPDATE core.models SET lock_level = 'content', lock_reason = :r, locked_at = now(), locked_by = :u,
                                frozen_at = now(), frozen_by = :u, frozen_note = :n WHERE id = :m"""),
                 {"r": f"Frozen: {note}".strip(": ")[:500], "u": user.username, "n": (note or "").strip()[:1000], "m": m["_id"]})
    return {"model": str(m["id"]), "message": f"{m['name']} is frozen: read only for good (it can still be copied, compared and reported on)."}


def unfreeze(conn, model: Any, user) -> dict:
    m = repo.get_model(conn, model)
    if perms.SUPER_ADMIN not in (user.roles or ()):
        raise EditError("Only a Super Admin unfreezes a model.", 403)
    if not m.get("frozen_at"):
        raise EditError(f"{m['name']} is not frozen.", 409)
    conn.execute(text("SELECT set_config('eax.actor', :a, true)"), {"a": user.username})
    conn.execute(text("""UPDATE core.models SET lock_level = 'none', lock_reason = '', frozen_at = NULL, frozen_by = NULL,
                                frozen_note = '' WHERE id = :m"""), {"m": m["_id"]})
    return {"model": str(m["id"]), "message": f"{m['name']} is no longer frozen."}


# ---------------------------------------------------------------- 13: detach and re-parent
def detach(conn, model: Any, user) -> dict:
    m = repo.get_model(conn, model)
    _admin(conn, user, m, "Detaching a model")
    if not m.get("parent_model_id"):
        raise EditError(f"{m['name']} has no parent model.", 409)
    conn.execute(text("UPDATE core.models SET parent_model_id = NULL WHERE id = :m"), {"m": m["_id"]})
    return {"model": str(m["id"]), "message": f"{m['name']} no longer derives from {m['parent_model_name']}: it is a model of its own."}


def reparent(conn, model: Any, user, parent: Any) -> dict:
    m = repo.get_model(conn, model)
    p = repo.get_model(conn, parent)
    _admin(conn, user, m, "Moving a model under another")
    if p["kind"] != "project":
        raise EditError("A model derives only from a project model.")
    if str(p["id"]) == str(m["id"]):
        raise EditError("A model cannot be its own parent.")
    below = {r["g"] for r in _rows(conn, """WITH RECURSIVE d AS (SELECT id FROM core.models WHERE id = :m
                                               UNION ALL SELECT c.id FROM core.models c JOIN d ON c.parent_model_id = d.id)
                                             SELECT x.guid::text AS g FROM core.models x JOIN d ON d.id = x.id""", m=m["_id"])}
    if str(p["id"]) in below:
        raise EditError(f"{p['name']} derives from {m['name']}: that would make a loop.")
    conn.execute(text("UPDATE core.models SET parent_model_id = :p WHERE id = :m"), {"p": p["_id"], "m": m["_id"]})
    return {"model": str(m["id"]), "message": f"{m['name']} now derives from {p['name']} (it merges back into it)."}


# ---------------------------------------------------------------- 14: split
def split(conn, model: Any, user, d: dict) -> dict:
    """Part of a model (entity types and/or chosen entities, with the relationships between them) into a new model:
    a child (it merges back) or a separate one; copied, or moved (taken out of this model as one commit)."""
    from . import commits as cm
    from . import model_ops as mo
    m = repo.get_model(conn, model)
    if d.get("move"):
        _admin(conn, user, m, "Moving part of a model out")
    types = {str(x).lower() for x in d.get("entity_types") or []}
    keys = {str(x) for x in d.get("entities") or []}
    if not types and not keys:
        raise EditError("Choose the entity types or entities that go into the new model.")
    if not (d.get("name") or "").strip():
        raise EditError("Give the new model a name.")
    content = mo.package_content(conn, str(m["id"]))
    picked = {code: [r for r in rows if code.lower() in types or str(r["key"]) in keys] for code, rows in content["entities"].items()}
    picked = {c: r for c, r in picked.items() if r}
    chosen = {str(r["key"]) for rows in picked.values() for r in rows}
    if not chosen:
        raise EditError("Nothing chosen is in the model.")
    for rows in picked.values():
        for r in rows:
            if r.get("parent") and str(r["parent"]) not in chosen:
                r["parent"] = ""
    rels = [r for r in content["relationships"] if str(r["source"]) in chosen and str(r["target"]) in chosen]
    spec = {"kind": "project", "name": d["name"].strip(), "source": str(m["id"]), "copy": "metamodel",
            "description": (d.get("description") or "").strip() or f"Split from {m['name']}."}
    if d.get("child", True) and m["kind"] == "project":
        spec["parent"] = str(m["id"])
    new = mo.create_model(conn, user.username, spec)["model"]
    counts = mo.load_content(conn, new["_id"], picked, rels, mo.metamodel_spec(conn, str(new["id"])))
    moved = 0
    if d.get("move"):
        items = [("entity.delete", {"entity": k}) for k in chosen]
        res = cm.record_many(conn, m["id"], user.username, items)
        ids = [r["kept"]["change"] for r in res if r.get("ok") and r.get("kept")]
        if ids:
            cm.commit(conn, m["id"], user, None, ids, None, f"Moved to {new['name']} (split)")
        moved = len(ids)
    return {"model": {"id": str(new["id"]), "name": new["name"]}, "counts": counts, "moved": moved,
            "message": f"{new['name']} made with {len(chosen)} entities and {len(rels)} relationships" +
                       (f"; {moved} taken out of {m['name']}" if moved else "") + "."}


# ---------------------------------------------------------------- 18: extend the metamodel from another model
def extend_preview(conn, model: Any, source: Any) -> dict:
    from . import model_ops as mo
    have = mo.metamodel_spec(conn, str(repo.get_model(conn, model)["id"]))
    src = mo.metamodel_spec(conn, str(repo.get_model(conn, source)["id"]))
    mine_t = {t["code"].lower() for t in have["entity_types"]}
    mine_r = {r["code"].lower() for r in have["relationship_types"]}
    mine_a = {a["code"].lower() for a in have["attributes"]}
    return {"entity_types": [{"code": t["code"], "name": t.get("name") or t["code"], "domain": t.get("domain")}
                             for t in src["entity_types"] if t["code"].lower() not in mine_t],
            "relationship_types": [{"code": r["code"], "name": r.get("name") or r["code"]}
                                   for r in src["relationship_types"] if r["code"].lower() not in mine_r],
            "attributes": [{"code": a["code"], "name": a.get("name") or a["code"], "data_type": a.get("data_type")}
                           for a in src["attributes"] if a["code"].lower() not in mine_a]}


def extend_metamodel(conn, model: Any, user, source: Any, picks: dict) -> dict:
    """Adds the chosen entity types, relationship types and attributes of another model's metamodel (with their
    domains, pick lists and the allowed relationships between what the model then has) as one metamodel version."""
    from . import model_ops as mo
    from . import reports
    m = repo.get_model(conn, model)
    _admin(conn, user, m, "Extending the metamodel")
    src = mo.metamodel_spec(conn, str(repo.get_model(conn, source)["id"]))
    have = mo.metamodel_spec(conn, str(m["id"]))
    merged = json.loads(json.dumps(have, default=str))
    want_t = {str(x).lower() for x in picks.get("entity_types") or []}
    want_r = {str(x).lower() for x in picks.get("relationship_types") or []}
    want_a = {str(x).lower() for x in picks.get("attributes") or []}
    if not (want_t or want_r or want_a):
        raise EditError("Choose what to add.")
    for t in src["entity_types"]:
        if t["code"].lower() in want_t:
            for a in t.get("attributes") or []:
                want_a.add(a["attribute"].lower())
    known = {s: {str(i["code"]).lower() for i in merged[s]} for s in ("domains", "pick_lists", "attributes", "entity_types", "relationship_types")}
    added = {"entity_types": 0, "relationship_types": 0, "attributes": 0}
    for a in src["attributes"]:
        if a["code"].lower() in want_a and a["code"].lower() not in known["attributes"]:
            merged["attributes"].append(a)
            added["attributes"] += 1
            if a.get("pick_list") and str(a["pick_list"]).lower() not in known["pick_lists"]:
                merged["pick_lists"] += [p for p in src["pick_lists"] if str(p["code"]).lower() == str(a["pick_list"]).lower()]
    for t in src["entity_types"]:
        if t["code"].lower() in want_t and t["code"].lower() not in known["entity_types"]:
            if t.get("domain") and str(t["domain"]).lower() not in known["domains"]:
                merged["domains"] += [domain for domain in src["domains"] if str(domain["code"]).lower() == str(t["domain"]).lower()]
                known["domains"].add(str(t["domain"]).lower())
            merged["entity_types"].append(t)
            added["entity_types"] += 1
    for r in src["relationship_types"]:
        if r["code"].lower() in want_r and r["code"].lower() not in known["relationship_types"]:
            merged["relationship_types"].append(r)
            added["relationship_types"] += 1
    types_now = {t["code"].lower() for t in merged["entity_types"]}
    rels_now = {r["code"].lower() for r in merged["relationship_types"]}
    have_allowed = {(a["source"].lower(), a["relationship"].lower(), a["target"].lower()) for a in merged["allowed"]}
    for a in src.get("allowed") or []:
        k = (a["source"].lower(), a["relationship"].lower(), a["target"].lower())
        if k not in have_allowed and k[0] in types_now and k[2] in types_now and k[1] in rels_now:
            merged["allowed"].append(a)
    version = conn.execute(text("SELECT core.publish_metamodel_version(:m, :n)"),
                           {"m": m["_id"], "n": f"Extended from another model's metamodel ({user.username})"}).scalar_one()
    mo.apply_spec(conn, m["_id"], merged, "merge")
    reports.refresh_typed_views(conn)
    return {"model": str(m["id"]), "metamodel_version": version, "added": added,
            "message": f"Added {added['entity_types']} entity types, {added['relationship_types']} relationship types and "
                       f"{added['attributes']} attributes (metamodel version {version})."}


# ---------------------------------------------------------------- 19: duplicates
def duplicates(conn, model: Any, entity_type: str | None = None, threshold: float = 0.88, attributes: list[str] | None = None,
               by_name: bool = True) -> dict:
    """Groups of likely duplicates (phase 21: eax.dedupe.candidates, by name and, when asked, by attributes)."""
    from . import dedupe
    return dedupe.candidates(conn, model, entity_type, attributes, threshold, by_name)


def merge_duplicates(conn, model: Any, user, keep: str, others: list[str], choices: dict | None = None) -> dict:
    """Keeps one entity and merges the others into it (phase 21: eax.dedupe.merge)."""
    from . import dedupe
    return dedupe.merge(conn, model, user, keep, others, choices)


# ---------------------------------------------------------------- 20: hand over
def hand_over(conn, model: Any, user, add: list[str], remove: list[str], owner: str | None = None) -> dict:
    """New Model Admins in, old ones out (a model keeps at least one), and the owner named on the model."""
    m = repo.get_model(conn, model)
    _admin(conn, user, m, "Handing a model over")
    add = sorted({u.strip().lower() for u in add or [] if u.strip()})
    remove = sorted({u.strip().lower() for u in remove or [] if u.strip()} - set(add))
    now = {r["u"] for r in _rows(conn, "SELECT lower(username) AS u FROM core.model_users WHERE model_id = :m AND role = :r",
                                 m=m["_id"], r=perms.MODEL_ADMIN)}
    if not (now | set(add)) - set(remove):
        raise EditError("A model keeps at least one Model Admin.")
    for u in add:
        conn.execute(text("""INSERT INTO core.model_users (model_id, username, role, created_by) VALUES (:m, :u, :r, :b)
                             ON CONFLICT (model_id, username, role) DO NOTHING"""),
                     {"m": m["_id"], "u": u, "r": perms.MODEL_ADMIN, "b": user.username})
    if remove:
        conn.execute(text("DELETE FROM core.model_users WHERE model_id = :m AND role = :r AND lower(username) = ANY (CAST(:u AS text[]))"),
                     {"m": m["_id"], "r": perms.MODEL_ADMIN, "u": remove})
    if owner is not None:
        conn.execute(text("UPDATE core.models SET owner = :o WHERE id = :m"), {"o": owner.strip(), "m": m["_id"]})
    return {"model": str(m["id"]), "message": f"Model Admins of {m['name']}: {', '.join(sorted((now | set(add)) - set(remove)))}."}


# ---------------------------------------------------------------- the family of a model, for the wizards' choices
def family(conn, model: Any) -> dict:
    """The model's parent, children, the library model it was built from, and whether it is frozen."""
    m = repo.get_model(conn, model)
    kids = _rows(conn, """SELECT guid::text AS id, name FROM core.models WHERE parent_model_id = :m AND NOT is_deleted ORDER BY name""",
                 m=m["_id"])
    src = None
    if m.get("source_model_id"):
        s = repo.get_model(conn, str(m["source_model_id"]))
        src = {"id": str(s["id"]), "name": s["name"], "kind": s["kind"], "version_label": s.get("version_label")}
    return {"id": str(m["id"]), "name": m["name"], "kind": m["kind"], "frozen": bool(m.get("frozen_at")), "frozen_at": m.get("frozen_at"),
            "frozen_by": m.get("frozen_by"), "lock_level": m.get("lock_level"),
            "parent": {"id": str(m["parent_model_id"]), "name": m["parent_model_name"]} if m.get("parent_model_id") else None,
            "children": kids, "source": src}
