"""Model tags (build phase 8.3, D172).

A tag is a frozen snapshot of a model under a name: its metamodel (as the eax-metamodel/1 document) and every
entity, value and relationship as they are at that moment (committed content only). Anyone who may change the
model's content tags it; a locked tag is never changed or deleted (the database refuses).

Making a tag the latest is a complete override, like restoring an old backup on top of the model: the current
version is tagged first (kind before-restore, so nothing is lost and it can be made the latest again), then
the model gets the tag's metamodel (entity types, attributes, relationship types and pick lists added since
are removed) and the tag's content (entities and relationships added since are deleted, the others put back
as they were), as one commit of kind restore. Model Admins only, on an unlocked project model.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import commits as cm
from . import content as ct
from . import model_ops as mo
from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError, _db_message


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def _one(conn, sql: str, **p) -> dict | None:
    r = _rows(conn, sql, **p)
    return r[0] if r else None


def _exec(conn, sql: str, **p):
    return conn.execute(text(sql), p)


# ---------------------------------------------------------------- the model as it is, in one go
def snapshot(conn, m: dict) -> dict:
    """Every entity and relationship of a model (committed, not deleted) as the snapshot states eax.commits
    uses (snap_entity, snap_relationship), read in a few queries, keyed by guid."""
    mid = m["_id"]
    ents = _rows(conn, """SELECT e.id, e.guid, e.origin_guid, e.name, e.description, e.display_id, e.status_code AS status, e.tags,
                                 p.guid AS parent, t.code AS type_code, t.name AS entity_type, l.name AS domain
                            FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                            JOIN core.layers l ON l.id = t.layer_id
                            LEFT JOIN core.entities p ON p.id = e.parent_entity_id
                           WHERE e.model_id = :m AND NOT e.is_deleted ORDER BY t.code, e.display_id""", m=mid)
    vals = _rows(conn, """SELECT av.id, av.entity_id, at.code, av.value_text, av.value_number, av.value_date, av.value_bool,
                                 av.value_ref, r.guid AS ref_guid
                            FROM core.attribute_values av JOIN core.attribute_types at ON at.id = av.attribute_type_id
                            LEFT JOIN core.entities r ON r.id = av.value_ref
                           WHERE av.model_id = :m AND av.entity_id IS NOT NULL AND NOT av.is_deleted""", m=mid)
    rels = _rows(conn, """SELECT r.guid, r.origin_guid, r.name, rt.code AS type_code, rt.name AS relationship_type, rt.verb,
                                 s.id AS sid, s.guid AS source, s.name AS source_name, t.id AS tid, t.guid AS target,
                                 t.name AS target_name
                            FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
                            JOIN core.entities s ON s.id = r.source_entity_id AND NOT s.is_deleted
                            JOIN core.entities t ON t.id = r.target_entity_id AND NOT t.is_deleted
                           WHERE r.model_id = :m AND NOT r.is_deleted ORDER BY rt.code, s.name, t.name""", m=mid)
    by_id: dict[int, dict] = {}
    entities: dict[str, dict] = {}
    for e in ents:
        tags = e["tags"] or []
        if isinstance(tags, str):
            tags = [t for t in tags.strip("{}").split(",") if t]
        st = {"kind": "entity", "guid": str(e["guid"]), "deleted": False, "name": e["name"], "description": e["description"] or "",
              "display_id": e["display_id"], "status": e["status"], "tags": sorted(tags), "parent": cm._s(e["parent"]),
              "type_code": e["type_code"], "entity_type": e["entity_type"], "domain": e["domain"],
              "origin": cm._s(e["origin_guid"]), "values": {}, "_value_ids": [], "relationships": []}
        by_id[e["id"]] = st
        entities[st["guid"]] = st
    for v in vals:
        st = by_id.get(v["entity_id"])
        if st is None:
            continue
        c = cm._canon(v)
        if c is not None:
            st["values"][v["code"]] = c
        st["_value_ids"].append(v["id"])
    relationships: dict[str, dict] = {}
    for r in rels:
        g = str(r["guid"])
        relationships[g] = {"kind": "relationship", "guid": g, "deleted": False, "name": r["name"] or "", "type_code": r["type_code"],
                            "relationship_type": r["relationship_type"], "verb": r["verb"], "origin": cm._s(r["origin_guid"]),
                            "source": str(r["source"]), "source_name": r["source_name"], "target": str(r["target"]),
                            "target_name": r["target_name"]}
        for k in ("sid", "tid"):
            if r[k] in by_id:
                by_id[r[k]]["relationships"].append(g)
    for st in entities.values():
        st["relationships"] = sorted(set(st["relationships"]))
    return {"entities": entities, "relationships": relationships}


def side_of_model(conn, model: Any) -> dict:
    """A model as it is now, ready to compare or tag: its metamodel and snapshot."""
    m = repo.get_model(conn, model)
    return {"kind": "model", "model_id": str(m["id"]), "model": m["name"], "tag_id": None, "tag": None,
            "commit": cm.latest(conn, str(m["id"]))["number"], "metamodel_version": m["metamodel_version"],
            "label": f"{m['name']} (now)", "spec": mo.metamodel_spec(conn, str(m["id"])), "snapshot": snapshot(conn, m)}


# ---------------------------------------------------------------- tags
def _may_tag(conn, user, m: dict) -> None:
    if m["kind"] == "template":
        raise EditError("A root metamodel has no content to tag; its versions are kept in its metamodel history.", 409)
    roles = set(perms.model_roles(conn, user.username, m["id"]))
    if not (perms.SUPER_ADMIN in user.roles or roles & set(perms.MODEL_PERMISSIONS["model.content"])):
        raise EditError(f"Tagging {m['name']} needs a role that changes its content (Architect, Committer, Model Sub Admin "
                        "or Model Admin).", 403)


def _tag_row(conn, m: dict, tag: Any) -> dict:
    g = repo._as_guid(tag)
    t = _one(conn, "SELECT * FROM core.model_tags WHERE guid = :g AND model_id = :m", g=str(g), m=m["_id"]) if g else None
    if not t:
        raise EditError("No such tag on this model.", 404)
    return t


def _tag_out(t: dict) -> dict:
    return {"id": str(t["guid"]), "name": t["name"], "description": t["description"], "kind": t["kind"], "locked": t["is_locked"],
            "commit": t["commit_number"], "metamodel_version": t["metamodel_version"], "entities": t["entity_count"],
            "relationships": t["relationship_count"], "created_by": t["created_by"], "created_at": t["created_at"],
            "locked_by": t["locked_by"], "locked_at": t["locked_at"], "restored_at": t["restored_at"], "restored_by": t["restored_by"]}


def _insert(conn, m: dict, name: str, description: str, kind: str, actor: str) -> dict:
    side = side_of_model(conn, str(m["id"]))
    snap = dict(side["snapshot"])
    try:
        row = _one(conn, """INSERT INTO core.model_tags (model_id, name, description, kind, commit_number, metamodel_version, spec,
                                                         snapshot, entity_count, relationship_count, created_by)
                            VALUES (:m, :n, :d, :k, :c, :v, CAST(:spec AS jsonb), CAST(:snap AS jsonb), :ec, :rc, :by) RETURNING *""",
                   m=m["_id"], n=name.strip(), d=(description or "").strip(), k=kind, c=side["commit"], v=side["metamodel_version"],
                   spec=json.dumps(side["spec"], default=str), snap=json.dumps(snap, default=str),
                   ec=len(snap["entities"]), rc=len(snap["relationships"]), by=actor.lower())
    except DBAPIError as exc:
        if "model_tags_name_idx" in str(exc.orig):
            raise EditError(f"{m['name']} already has a tag called '{name.strip()}'.", 409) from exc
        raise EditError(_db_message(exc), 409) from exc
    _hold_views(conn, m, row)
    return row


def _hold_views(conn, m: dict, row: dict) -> None:
    """A tag keeps the drawn views as they are now (D354, D405): the views service holds each view's latest version for
    it (never dropped while the tag is there); the tag's snapshot lists which. The service being off or down never stops
    a tag: the snapshot says the views were not kept."""
    from . import views_client as vc
    try:
        held = {"drawn_views": vc.hold_for_tag(m["id"], row["guid"])}
    except vc.ViewsDown as exc:
        held = {"drawn_views": [], "drawn_views_note": f"The drawn views were not kept with this tag: {exc}."}
    conn.execute(text("UPDATE core.model_tags SET snapshot = snapshot || CAST(:h AS jsonb) WHERE id = :id"),
                 {"h": json.dumps(held), "id": row["id"]})


def list_tags(conn, model: Any) -> dict:
    m = repo.get_model(conn, model)
    rows = _rows(conn, """SELECT id, guid, name, description, kind, is_locked, commit_number, metamodel_version, entity_count,
                                 relationship_count, created_by, created_at, locked_by, locked_at, restored_at, restored_by
                            FROM core.model_tags WHERE model_id = :m ORDER BY created_at DESC, id DESC""", m=m["_id"])
    return {"model": {"id": str(m["id"]), "name": m["name"]}, "tags": [_tag_out(t) for t in rows],
            "now": {"commit": cm.latest(conn, str(m["id"]))["number"], "metamodel_version": m["metamodel_version"]}}


def list_all_tags(conn) -> dict:
    """The Tags screen: the tags of every model the person may read (row-level security on the models decides),
    newest first."""
    rows = _rows(conn, """SELECT t.id, t.guid, t.name, t.description, t.kind, t.is_locked, t.commit_number, t.metamodel_version,
                                 t.entity_count, t.relationship_count, t.created_by, t.created_at, t.locked_by, t.locked_at,
                                 t.restored_at, t.restored_by, m.guid AS model_guid, m.name AS model_name, m.kind_code AS model_kind
                            FROM core.model_tags t JOIN core.models m ON m.id = t.model_id
                           ORDER BY t.created_at DESC, t.id DESC""")
    return {"tags": [{**_tag_out(t), "model": {"id": str(t["model_guid"]), "name": t["model_name"], "kind": t["model_kind"]}}
                     for t in rows]}


def _spec_names(spec: dict) -> tuple[dict, dict, dict]:
    domains = {x["code"]: x["name"] for x in spec.get("domains") or []}
    types = {x["code"]: {"name": x["name"], "domain": domains.get(x.get("domain"), x.get("domain") or "")} for x in spec.get("entity_types") or []}
    attrs = {x["code"]: x["name"] for x in spec.get("attributes") or []}
    return domains, types, attrs


def get_tag(conn, model: Any, tag: Any) -> dict:
    """One tag's page: its details and its frozen contents (entities by type, relationships, the metamodel in short)."""
    m = repo.get_model(conn, model)
    t = _tag_row(conn, m, tag)
    spec, snap = cm._json(t["spec"]) or {}, cm._json(t["snapshot"]) or {}
    _domains, types, _attrs = _spec_names(spec)
    ents = snap.get("entities") or {}
    entities = sorted(({"id": g, "name": e.get("name") or "", "type_code": e.get("type_code"),
                        "entity_type": e.get("entity_type") or types.get(e.get("type_code"), {}).get("name") or e.get("type_code"),
                        "domain": e.get("domain") or types.get(e.get("type_code"), {}).get("domain") or "",
                        "display_id": e.get("display_id") or "", "status": e.get("status") or "",
                        "parent": (ents.get(e.get("parent")) or {}).get("name") if e.get("parent") else None,
                        "values": len(e.get("values") or {})} for g, e in ents.items()),
                      key=lambda x: (x["domain"], x["entity_type"], x["name"].lower()))
    rels = sorted(({"id": g, "relationship_type": r.get("relationship_type") or r.get("type_code"), "verb": r.get("verb") or "",
                    "source": r.get("source"), "source_name": r.get("source_name") or (ents.get(r.get("source")) or {}).get("name"),
                    "target": r.get("target"), "target_name": r.get("target_name") or (ents.get(r.get("target")) or {}).get("name"),
                    "name": r.get("name") or ""} for g, r in (snap.get("relationships") or {}).items()),
                  key=lambda x: (x["relationship_type"] or "", (x["source_name"] or "").lower()))
    by_type: dict[str, dict] = {}
    for e in entities:
        b = by_type.setdefault(e["type_code"], {"code": e["type_code"], "name": e["entity_type"], "domain": e["domain"], "count": 0})
        b["count"] += 1
    return {**_tag_out(t), "model": {"id": str(m["id"]), "name": m["name"], "kind": m["kind"]},
            "metamodel": {"domains": len(spec.get("domains") or []), "entity_types": len(spec.get("entity_types") or []),
                          "attributes": len(spec.get("attributes") or []), "relationship_types": len(spec.get("relationship_types") or []),
                          "pick_lists": len(spec.get("pick_lists") or []), "rules": len(spec.get("rules") or [])},
            "types": sorted(by_type.values(), key=lambda b: (b["domain"], b["name"])), "entity_list": entities, "relationship_list": rels,
            "drawn_views": [{"id": v["id"], "name": v["name"], "version": v.get("version")} for v in snap.get("drawn_views") or []],
            "drawn_views_note": snap.get("drawn_views_note")}


def tag_drawn_view(conn, model: Any, tag: Any, view: str) -> dict:
    """A drawn view as the tag keeps it (D354): the version the views service holds for the tag, read only."""
    from . import views_client as vc
    m = repo.get_model(conn, model)
    t = _tag_row(conn, m, tag)
    try:
        return {"tag": t["name"], **vc.tag_view(m["id"], t["guid"], view)}
    except vc.ViewsDown as exc:
        if exc.status == 404:
            raise repo.NotFound(f"The tag {t['name']} keeps no drawn view {view!r}.") from exc
        raise EditError(f"The drawn view cannot be opened just now: {exc}", 503) from exc


def tag_entity(conn, model: Any, tag: Any, entity: Any) -> dict:
    """One entity as it was in a tag: its fields, attribute values and relationships."""
    m = repo.get_model(conn, model)
    t = _tag_row(conn, m, tag)
    spec, snap = cm._json(t["spec"]) or {}, cm._json(t["snapshot"]) or {}
    _domains, types, attrs = _spec_names(spec)
    ents = snap.get("entities") or {}
    e = ents.get(str(entity))
    if not e:
        raise EditError(f"The tag '{t['name']}' has no such entity.", 404)
    rels = [{"id": g, "direction": "out" if r.get("source") == str(entity) else "in",
             "relationship_type": r.get("relationship_type") or r.get("type_code"), "verb": r.get("verb") or "",
             "other": r.get("target") if r.get("source") == str(entity) else r.get("source"),
             "other_name": r.get("target_name") if r.get("source") == str(entity) else r.get("source_name")}
            for g, r in (snap.get("relationships") or {}).items() if str(entity) in (r.get("source"), r.get("target"))]
    for r in rels:
        r["in_tag"] = r["other"] in ents
    return {"tag": {"id": str(t["guid"]), "name": t["name"]}, "model": {"id": str(m["id"]), "name": m["name"]}, "id": str(entity),
            "name": e.get("name"), "description": e.get("description") or "", "display_id": e.get("display_id") or "",
            "status": e.get("status") or "", "tags": e.get("tags") or [],
            "entity_type": e.get("entity_type") or types.get(e.get("type_code"), {}).get("name"),
            "domain": e.get("domain") or types.get(e.get("type_code"), {}).get("domain") or "",
            "parent": {"id": e["parent"], "name": (ents.get(e["parent"]) or {}).get("name")} if e.get("parent") else None,
            "values": sorted(({"code": k, "label": attrs.get(k, k), "value": v} for k, v in (e.get("values") or {}).items()),
                             key=lambda x: x["label"].lower()),
            "relationships": sorted(rels, key=lambda r: (r["direction"], r["relationship_type"] or "", (r["other_name"] or "").lower())),
            "exists_now": bool(_one(conn, "SELECT 1 AS x FROM core.entities WHERE guid = CAST(:g AS uuid) AND model_id = :m AND NOT is_deleted",
                                    g=str(entity), m=m["_id"]))}


def check_tag(conn, model: Any, user, name: str) -> dict:
    """What creating a tag checks before it is queued as a background task (D192): rights, a name, not taken."""
    m = repo.get_model(conn, model)
    _may_tag(conn, user, m)
    if not (name or "").strip():
        raise EditError("Give the tag a name, for example Baseline 2026.")
    if _one(conn, "SELECT 1 AS x FROM core.model_tags WHERE model_id = :m AND lower(name) = lower(:n)", m=m["_id"], n=name.strip()):
        raise EditError(f"{m['name']} already has a tag called '{name.strip()}'.", 409)
    return m


def create_tag(conn, model: Any, user, name: str, description: str = "", lock: bool = False) -> dict:
    """Tags the model as it is now (committed content and the metamodel)."""
    m = repo.get_model(conn, model)
    _may_tag(conn, user, m)
    if not (name or "").strip():
        raise EditError("Give the tag a name, for example Baseline 2026.")
    t = _insert(conn, m, name, description, "manual", user.username)
    from . import kpis  # every tag keeps the KPIs as they are now (phase 24, D365)
    kpis.on_tag(conn, m, t, user.username)
    if lock:
        t = _one(conn, """UPDATE core.model_tags SET is_locked = true, locked_by = :u, locked_at = now() WHERE id = :i RETURNING *""",
                 u=user.username.lower(), i=t["id"])
    return _tag_out(t)


def update_tag(conn, model: Any, user, tag: Any, name: str | None = None, description: str | None = None,
               locked: bool | None = None) -> dict:
    """Renames or describes a tag (not when locked), or locks it; unlocking needs the Model Admin role."""
    m = repo.get_model(conn, model)
    _may_tag(conn, user, m)
    t = _tag_row(conn, m, tag)
    if locked is False and t["is_locked"]:
        if not (perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"])):
            raise EditError("Unlocking a tag needs the Model Admin role on the model.", 403)
        t = _one(conn, "UPDATE core.model_tags SET is_locked = false, locked_by = NULL, locked_at = NULL WHERE id = :i RETURNING *", i=t["id"])
    if name is not None or description is not None:
        if t["is_locked"]:
            raise EditError(f"The tag '{t['name']}' is locked: it cannot be changed.", 409)
        try:
            t = _one(conn, "UPDATE core.model_tags SET name = :n, description = :d WHERE id = :i RETURNING *",
                     n=(name if name is not None else t["name"]).strip() or t["name"],
                     d=(description if description is not None else t["description"]).strip(), i=t["id"])
        except DBAPIError as exc:
            raise EditError(f"{m['name']} already has a tag with that name." if "model_tags_name_idx" in str(exc.orig)
                            else _db_message(exc), 409) from exc
    if locked is True and not t["is_locked"]:
        t = _one(conn, "UPDATE core.model_tags SET is_locked = true, locked_by = :u, locked_at = now() WHERE id = :i RETURNING *",
                 u=user.username.lower(), i=t["id"])
    return _tag_out(t)


def delete_tag(conn, model: Any, user, tag: Any) -> dict:
    m = repo.get_model(conn, model)
    _may_tag(conn, user, m)
    t = _tag_row(conn, m, tag)
    if t["is_locked"]:
        raise EditError(f"The tag '{t['name']}' is locked: it cannot be deleted.", 409)
    _exec(conn, "DELETE FROM core.model_tags WHERE id = :i", i=t["id"])
    return {"deleted": str(t["guid"])}


def tag_side(conn, tag: Any) -> dict:
    """A tag, ready to compare: its model, metamodel and snapshot (any model's tag the person may open)."""
    g = repo._as_guid(tag)
    t = _one(conn, "SELECT * FROM core.model_tags WHERE guid = :g", g=str(g)) if g else None
    if not t:
        raise EditError("No such tag.", 404)
    m = _one(conn, "SELECT guid, name FROM core.models WHERE id = :i", i=t["model_id"])
    repo.get_model(conn, str(m["guid"]))   # only a tag of a model the person may open
    return {"kind": "tag", "model_id": str(m["guid"]), "model": m["name"], "tag_id": str(t["guid"]), "tag": t["name"],
            "commit": t["commit_number"], "metamodel_version": t["metamodel_version"], "label": f"{m['name']}: {t['name']}",
            "spec": cm._json(t["spec"]), "snapshot": cm._json(t["snapshot"]), "created_at": t["created_at"]}


def download_tag(conn, model: Any, tag: Any, fmt: str = "xlsx", actor: str | None = None) -> tuple[bytes, str, str]:
    """A tag as a model package (Excel or zip): to keep, to load elsewhere, or to merge into another model."""
    m = repo.get_model(conn, model)
    t = _tag_row(conn, m, tag)
    side = tag_side(conn, str(t["guid"]))
    content: dict = {"entities": {}, "relationships": []}
    for e in side["snapshot"]["entities"].values():
        row = {"key": e["guid"], "display_id": e["display_id"], "name": e["name"], "description": e["description"],
               "parent": e["parent"] or "", "status": e["status"], **e["values"]}
        content["entities"].setdefault(e["type_code"], []).append(row)
    for r in side["snapshot"]["relationships"].values():
        content["relationships"].append({"key": r["guid"], "type": r["type_code"], "source": r["source"], "target": r["target"],
                                         "name": r["name"], "description": "", "status": "published"})
    manifest = mo._manifest(conn, m, side["spec"], content, actor)
    manifest["model"]["name"] = f"{m['name']} (tag {t['name']})"
    manifest["tag"] = {"name": t["name"], "created_at": str(t["created_at"]), "commit": t["commit_number"]}
    base = "".join(ch if ch.isalnum() or ch in "._" else "-" for ch in f"{m['name']} {t['name']}").strip("-")
    return mo.write_package(manifest, side["spec"], content, None, fmt, base)


# ---------------------------------------------------------------- making a tag the latest (a complete override)
def _drop_entity(conn, m: dict, guid: str) -> None:
    """Deletes an entity for a restore: its values, its relationships, and links to it (parts and attribute
    references; the tag's own parents and references are put back afterwards)."""
    e = _one(conn, "SELECT id FROM core.entities WHERE guid = CAST(:g AS uuid) AND model_id = :m AND NOT is_deleted", g=guid, m=m["_id"])
    if not e:
        return
    _exec(conn, "UPDATE core.entities SET parent_entity_id = NULL WHERE parent_entity_id = :e", e=e["id"])
    _exec(conn, "UPDATE core.attribute_values SET is_deleted = true WHERE value_ref = :e AND NOT is_deleted", e=e["id"])
    _exec(conn, "UPDATE core.attribute_values SET is_deleted = true WHERE entity_id = :e AND NOT is_deleted", e=e["id"])
    _exec(conn, """UPDATE core.relationships SET is_deleted = true WHERE (source_entity_id = :e OR target_entity_id = :e)
                   AND NOT is_deleted""", e=e["id"])
    _exec(conn, "UPDATE core.entities SET is_deleted = true WHERE id = :e", e=e["id"])


def _remove_metamodel_extras(conn, m: dict, spec: dict) -> int:
    """Removes what the tag's metamodel does not have: entity types, relationship types, attributes, attributes
    on types, pick lists and domains (their content is gone by now)."""
    mid = m["_id"]
    n = 0
    codes = {k: {str(i["code"]).lower() for i in spec.get(k) or []} for k in ("entity_types", "relationship_types", "attributes",
                                                                                "pick_lists", "domains")}
    on_type = {(t["code"].lower(), str(i["attribute"]).lower()) for t in spec.get("entity_types") or [] for i in t.get("attributes") or []}
    on_rel = {(r["code"].lower(), str(i["attribute"]).lower()) for r in spec.get("relationship_types") or []
              for i in r.get("attributes") or []}
    on_map = {(str(a["source"]).lower(), str(a["relationship"]).lower(), str(a["target"]).lower(), str(i["attribute"]).lower())
              for a in spec.get("allowed") or [] for i in a.get("attributes") or []}      # limited to some mappings (D564)
    on_rel |= {(r, at) for _s, r, _t, at in on_map}
    for r in _rows(conn, """SELECT x.id, s.code AS s, rt.code AS r, t.code AS t, a.code AS a
                              FROM core.item_attribute_mappings x JOIN core.item_attributes i ON i.id = x.item_attribute_id
                              JOIN core.attribute_types a ON a.id = i.attribute_type_id
                              JOIN core.allowed_relationships ar ON ar.id = x.allowed_relationship_id
                              JOIN core.entity_types s ON s.id = ar.source_type_id JOIN core.entity_types t ON t.id = ar.target_type_id
                              JOIN core.relationship_types rt ON rt.id = ar.relationship_type_id
                             WHERE x.model_id = :m AND NOT x.is_deleted""", m=mid):
        if (r["s"].lower(), r["r"].lower(), r["t"].lower(), r["a"].lower()) not in on_map:
            _exec(conn, "UPDATE core.item_attribute_mappings SET is_deleted = true WHERE id = :i", i=r["id"])
            n += 1
    for r in _rows(conn, """SELECT i.id, t.code AS t, rt.code AS r, a.code AS a FROM core.item_attributes i
                              JOIN core.attribute_types a ON a.id = i.attribute_type_id
                              LEFT JOIN core.entity_types t ON t.id = i.entity_type_id
                              LEFT JOIN core.relationship_types rt ON rt.id = i.relationship_type_id
                             WHERE i.model_id = :m AND NOT i.is_deleted""", m=mid):
        key = (str(r["t"] or r["r"]).lower(), r["a"].lower())
        if (r["t"] and key not in on_type) or (r["r"] and key not in on_rel):
            _exec(conn, "UPDATE core.item_attributes SET is_deleted = true WHERE id = :i", i=r["id"])
            n += 1
    for table, section in (("entity_types", "entity_types"), ("relationship_types", "relationship_types")):
        for r in _rows(conn, f"SELECT id, code FROM core.{table} WHERE model_id = :m AND NOT is_deleted", m=mid):
            if r["code"].lower() not in codes[section]:
                col = "source_type_id" if table == "entity_types" else "relationship_type_id"
                _exec(conn, f"UPDATE core.allowed_relationships SET is_deleted = true WHERE model_id = :m AND NOT is_deleted AND "
                            f"({col} = :i{' OR target_type_id = :i' if table == 'entity_types' else ''})", m=mid, i=r["id"])
                if table == "entity_types":
                    _exec(conn, "UPDATE core.validation_rules SET is_deleted = true WHERE model_id = :m AND NOT is_deleted "
                                "AND entity_type_id = :i", m=mid, i=r["id"])
                _exec(conn, f"UPDATE core.{table} SET is_deleted = true WHERE id = :i", i=r["id"])
                n += 1
    for table, section in (("attribute_types", "attributes"), ("pick_lists", "pick_lists"), ("layers", "domains")):
        for r in _rows(conn, f"SELECT id, code FROM core.{table} WHERE model_id = :m AND NOT is_deleted", m=mid):
            if r["code"].lower() not in codes[section]:
                if table == "attribute_types":
                    _exec(conn, "UPDATE core.validation_rules SET is_deleted = true WHERE attribute_type_id = :i AND NOT is_deleted",
                          i=r["id"])
                    _exec(conn, "UPDATE core.attribute_values SET is_deleted = true WHERE attribute_type_id = :i AND NOT is_deleted",
                          i=r["id"])
                if table == "pick_lists":
                    _exec(conn, "UPDATE core.attribute_types SET pick_list_id = NULL WHERE pick_list_id = :i", i=r["id"])
                    _exec(conn, "UPDATE core.pick_list_values SET is_deleted = true WHERE pick_list_id = :i AND NOT is_deleted", i=r["id"])
                if table == "layers" and _one(conn, "SELECT 1 AS x FROM core.entity_types WHERE layer_id = :i AND NOT is_deleted", i=r["id"]):
                    continue
                _exec(conn, f"UPDATE core.{table} SET is_deleted = true WHERE id = :i", i=r["id"])
                n += 1
    # pick-list values the tag's lists do not have
    want = {str(p["code"]).lower(): {str(v) for v in p.get("values") or []} for p in spec.get("pick_lists") or []}
    for r in _rows(conn, """SELECT v.id, v.value, p.code FROM core.pick_list_values v JOIN core.pick_lists p ON p.id = v.pick_list_id
                             WHERE v.model_id = :m AND NOT v.is_deleted AND NOT p.is_deleted""", m=mid):
        if r["code"].lower() in want and r["value"] not in want[r["code"].lower()]:
            _exec(conn, "UPDATE core.pick_list_values SET is_deleted = true WHERE id = :i", i=r["id"])
            n += 1
    return n


def restore_tag(conn, model: Any, user, tag: Any, note: str = "") -> dict:
    """Makes a tag the latest version of the model (D172): the current version is tagged first, then the tag
    overwrites the model completely (metamodel and content) as one commit. To go back, restore the tag made
    of the current version."""
    m = repo.get_model(conn, model)
    if not cm.uses_commits(m) or m.get("is_locked"):
        raise EditError("Only a project model is set back to a tag.", 409)
    mine = m.get("lock_level") == "maintenance" and (m.get("locked_by") or "").lower() == user.username.lower()
    if (m.get("lock_level") or "none") != "none" and not mine:   # a restore locks the model for its maker first (D236)
        raise EditError(f"{m['name']} is locked ({m['lock_level']}): unlock it to make a tag the latest.", 409)
    if not (perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"])):
        raise EditError(f"Making a tag the latest needs the Model Admin role on {m['name']} (it overwrites the metamodel).", 403)
    t = _tag_row(conn, m, tag)
    tag_spec, tag_snap = cm._json(t["spec"]), cm._json(t["snapshot"])
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    before = _insert(conn, m, f"Before restore {stamp} UTC",
                     f"{m['name']} as it was before {user.username} made the tag '{t['name']}' the latest. Make this tag the latest "
                     "to go back.", "before-restore", user.username)
    _exec(conn, "SELECT set_config('eax.actor', :a, true)", a=user.username)
    # 1. the tag's metamodel: everything it has comes back (renamed and re-added parts included); parts removed
    #    since (by an earlier restore) are taken back rather than added again, so their codes stay theirs
    for table, section in (("layers", "domains"), ("pick_lists", "pick_lists"), ("attribute_types", "attributes"),
                           ("entity_types", "entity_types"), ("relationship_types", "relationship_types")):
        codes = [str(i["code"]).lower() for i in tag_spec.get(section) or []]
        if codes:
            _exec(conn, f"""UPDATE core.{table} x SET is_deleted = false WHERE x.model_id = :m AND x.is_deleted
                             AND lower(x.code) = ANY (CAST(:c AS text[])) AND NOT EXISTS (
                                 SELECT 1 FROM core.{table} y WHERE y.model_id = x.model_id AND lower(y.code) = lower(x.code)
                                    AND NOT y.is_deleted)""", m=m["_id"], c=codes)
    version = conn.execute(text("SELECT core.publish_metamodel_version(:m, :n)"),
                           {"m": m["_id"], "n": f"Restored the tag '{t['name']}' ({user.username})"}).scalar_one()
    mo.apply_spec(conn, m["_id"], tag_spec, "merge")
    # 2. the tag's content, as one commit (each item keeps before and after)
    rc = cm._new_commit(conn, m, user, "restore", note or f"Restored the tag '{t['name']}'", [user.username])
    now = snapshot(conn, m)
    items = 0

    def item(kind: str, target: str, label: str, before_state: dict | None) -> None:
        nonlocal items
        after_state = cm._snap(conn, m, kind, target)
        if cm._same(cm._content(before_state), cm._content(after_state)):
            return
        cm._item(conn, rc["id"], None, user.username, f"restore:{kind}", {"tag": str(t["guid"])}, kind, target, label,
                 before_state, after_state)
        items += 1
    # entities the tag does not have go (their relationships with them)
    for g, cur in now["entities"].items():
        if g not in tag_snap["entities"]:
            b = cm.snap_entity(conn, m, g)
            _drop_entity(conn, m, g)
            item("entity", g, f"Remove {cur['entity_type']} '{cur['name']}'", b)
    # entities of the tag come back as they were (created again when they were never in this model)
    pending_parents = []
    for g, st in tag_snap["entities"].items():
        b = cm.snap_entity(conn, m, g)
        if b is None:
            try:
                ct.create_entity(conn, str(m["id"]), {"guid": g, "entity_type": st["type_code"], "name": st["name"],
                                                     "description": st.get("description") or "", "display_id": st.get("display_id")},
                                 user.username, light=True)
            except (EditError, repo.NotFound) as exc:
                raise EditError(f"'{st['name']}' cannot be restored: {exc}", 409) from exc
        state = {**st, "parent": None}
        cm._restore(conn, m, "entity", g, state, user.username, False)
        if st.get("parent"):
            pending_parents.append((g, st))
        item("entity", g, f"{'Restore' if b else 'Bring back'} {st['entity_type']} '{st['name']}'", b)
    for g, st in pending_parents:   # parents once every entity is back
        cm._restore(conn, m, "entity", g, st, user.username, False)
    # relationships: those the tag does not have go, the tag's come back
    now_rels = snapshot(conn, m)["relationships"]
    for g, cur in now_rels.items():
        if g not in tag_snap["relationships"]:
            b = cm.snap_relationship(conn, m, g)
            ct.delete_relationship(conn, str(m["id"]), g)
            item("relationship", g, f"Remove relationship: {cur['source_name']} {cur['verb'] or cur['relationship_type']} {cur['target_name']}", b)
    for g, st in tag_snap["relationships"].items():
        b = cm.snap_relationship(conn, m, g)
        if b is None:
            try:
                ct.add_relationship(conn, str(m["id"]), {"guid": g, "relationship_type": st["type_code"], "source": st["source"],
                                                         "target": st["target"], "name": st.get("name") or "", "allow_outside": True},
                                    user.username)
            except (EditError, repo.NotFound) as exc:
                raise EditError(f"The relationship {st['source_name']} {st['type_code']} {st['target_name']} cannot be restored: {exc}",
                                409) from exc
        else:
            cm._restore(conn, m, "relationship", g, st, user.username, False)
        item("relationship", g, f"Restore relationship: {st['source_name']} {st['verb'] or st['relationship_type']} {st['target_name']}", b)
    # 3. what the tag's metamodel does not have goes
    removed = _remove_metamodel_extras(conn, m, tag_spec)
    from . import reports
    reports.refresh_typed_views(conn)
    _exec(conn, "UPDATE core.model_tags SET restored_at = now(), restored_by = :u WHERE id = :i", u=user.username.lower(), i=t["id"])
    return {"restored": str(t["guid"]), "tag": t["name"], "commit": str(rc["guid"]), "commit_number": rc["number"], "items": items,
            "metamodel_version": version, "metamodel_removed": removed, "before_tag": _tag_out(before),
            "note": f"{m['name']} is now as tagged in '{t['name']}' (commit {rc['number']}, metamodel version {version}). "
                    f"What it was is kept in the tag '{before['name']}': restore that tag to go back."}
