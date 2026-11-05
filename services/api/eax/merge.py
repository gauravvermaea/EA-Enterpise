"""Merging a model into a model (build phase 8, D165).

A model package (the .zip or .xlsx EA Explorer makes, phase 4) is uploaded into an existing or draft model.
Its entities are matched to the model's by entity type and name (D165); for each match the fields and
values that differ are listed: one the model leaves empty is filled, one the model holds differently is a
conflict decided by the person (keep the model's, take the upload's, or type a value; or all one way).
Entity types, attributes and relationship types the model lacks are listed; a Model Admin may add them
(one new metamodel version), or that content is left out. Applying the merge records everything as one
set of uncommitted changes of the person who merged (eax.commits), committed like any other change.
"""

from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text

from . import commits as cm
from . import model_ops as mo
from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError

MAX_ROWS = 20000


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def _one(conn, sql: str, **p) -> dict | None:
    rows = _rows(conn, sql, **p)
    return rows[0] if rows else None


def _norm(value: Any, data_type: str | None) -> str | None:
    """A value as text in one spelling, so the model's and the upload's can be compared."""
    if value is None:
        return None
    v = str(value).strip()
    if v == "":
        return None
    if data_type in ("integer", "decimal", "currency", "percent"):
        try:
            return format(Decimal(v.replace(",", "").replace(" ", "").rstrip("%")).normalize(), "f")
        except InvalidOperation:
            return v
    if data_type == "date":
        return v[:10]
    if data_type == "boolean":
        return "Yes" if v.lower() in ("true", "yes", "1", "y") else "No" if v.lower() in ("false", "no", "0", "n") else v
    return v


def _metamodel_gaps(conn, m: dict, spec: dict, pkg: dict, whole: bool = False) -> dict:
    """What the upload uses that the model's metamodel lacks: entity types, attributes, attributes not on a
    type, relationship types. whole: everything the upload's metamodel has, used by its data or not (a merge
    without data)."""
    have = mo.metamodel_spec(conn, str(m["id"]))
    types = {t["code"].lower(): t for t in have["entity_types"]}
    attrs = {a["code"].lower() for a in have["attributes"]}
    rels = {r["code"].lower() for r in have["relationship_types"]}
    used_types = ({t["code"].lower() for t in spec.get("entity_types") or []} if whole
                  else {c.lower() for c, rows in pkg["entities"].items() if rows})
    gaps = {"entity_types": [], "attributes": [], "type_attributes": [], "relationship_types": []}
    for t in spec.get("entity_types") or []:
        code = t["code"].lower()
        if code not in used_types:
            continue
        if code not in types:
            gaps["entity_types"].append({"code": t["code"], "name": t.get("name") or t["code"],
                                         "entities": len(pkg["entities"].get(t["code"], []))})
            continue
        mine = {a["attribute"].lower() for a in types[code].get("attributes") or []}
        for a in t.get("attributes") or []:
            if a["attribute"].lower() not in mine:
                gaps["type_attributes"].append({"entity_type": t["code"], "attribute": a["attribute"]})
    for a in spec.get("attributes") or []:
        if a["code"].lower() not in attrs:
            gaps["attributes"].append({"code": a["code"], "name": a.get("name") or a["code"], "data_type": a.get("data_type")})
    used_rels = ({r["code"].lower() for r in spec.get("relationship_types") or []} if whole
                 else {str(r.get("type") or "").lower() for r in pkg["relationships"]})
    for r in spec.get("relationship_types") or []:
        if r["code"].lower() not in rels and r["code"].lower() in used_rels:
            gaps["relationship_types"].append({"code": r["code"], "name": r.get("name") or r["code"]})
    return gaps


def _target_state(conn, m: dict) -> tuple[dict, dict, dict]:
    """The model's entities by (type code, name), their values by attribute code, and attribute data types."""
    ents = _rows(conn, """SELECT e.id, e.guid, e.name, e.description, t.code AS type_code, p.guid AS parent
                            FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                            LEFT JOIN core.entities p ON p.id = e.parent_entity_id
                           WHERE e.model_id = :m AND NOT e.is_deleted ORDER BY e.id""", m=m["_id"])
    by_key: dict[tuple[str, str], dict] = {}
    for e in ents:
        by_key.setdefault((e["type_code"].lower(), e["name"].strip().lower()), e)
    by_id = {e["id"]: e for e in ents}
    for e in ents:
        e["values"] = {}
    for v in _rows(conn, """SELECT av.entity_id, at.code, at.data_type_code AS dt, av.value_text, av.value_number, av.value_date,
                                   av.value_bool, r.guid AS ref
                              FROM core.attribute_values av JOIN core.attribute_types at ON at.id = av.attribute_type_id
                              LEFT JOIN core.entities r ON r.id = av.value_ref
                             WHERE av.model_id = :m AND NOT av.is_deleted AND av.entity_id IS NOT NULL""", m=m["_id"]):
        e = by_id.get(v["entity_id"])
        if e is not None:
            raw = v["ref"] if v["ref"] is not None else next((v[k] for k in ("value_text", "value_number", "value_date", "value_bool")
                                                              if v[k] is not None), None)
            e["values"][v["code"].lower()] = _norm(raw, v["dt"])
    dtypes = {a["code"].lower(): (a["code"], a["data_type_code"]) for a in _rows(conn, """
        SELECT code, data_type_code FROM core.attribute_types WHERE model_id = :m AND NOT is_deleted""", m=m["_id"])}
    return by_key, by_id, dtypes


def analyse(conn, model: Any, data: bytes, filename: str, user, with_data: bool = True) -> dict:
    """Reads an uploaded model and works out what merging it would do; keeps the plan for apply.
    with_data False (or a package without data): only the metamodel is merged, the parts this model lacks."""
    m = repo.get_model(conn, model)
    if not cm.uses_commits(m):
        raise EditError("Merging is for working models (a project model, a draft or published).", 409)
    if m.get("is_locked"):
        raise EditError(f"{m['name']} is locked (read-only).", 409)
    pkg = mo.read_package(data, filename)
    spec = pkg["spec"]
    total = sum(len(v) for v in pkg["entities"].values())
    if total > MAX_ROWS:
        raise EditError(f"The upload has {total} entities; merge at most {MAX_ROWS} at a time.")
    has_data = any(pkg["entities"].values())
    with_data = bool(with_data and has_data)
    gaps = _metamodel_gaps(conn, m, spec, pkg, whole=not with_data)
    if not with_data:
        pkg = {**pkg, "entities": {}, "relationships": []}
    by_key, _by_id, dtypes = _target_state(conn, m)
    spec_types = {a["code"].lower(): a.get("data_type") for a in spec.get("attributes") or []}
    # every uploaded entity: matched (type and name) or new
    upload: dict[str, dict] = {}
    entities, conflicts = [], []
    for code, rows in pkg["entities"].items():
        for r in rows:
            key = str(r.get("key") or f"{code}:{r.get('display_id')}:{r.get('name')}")
            name = (r.get("name") or "").strip()
            if not name:
                continue
            match = by_key.get((code.lower(), name.lower()))
            upload[key] = {"type": code, "name": name, "match": str(match["guid"]) if match else None}
            item = {"key": key, "entity_type": code, "name": name, "action": "update" if match else "create",
                    "match": str(match["guid"]) if match else None, "fills": [], "conflicts": 0, "row": r}
            entities.append(item)
    # fields and values compared, now that every key is known (parents and references are keys)
    for item in entities:
        r = item.pop("row")
        target = by_key.get((item["entity_type"].lower(), item["name"].lower()))
        theirs: dict[str, Any] = {}
        if (r.get("description") or "").strip():
            theirs["description"] = r["description"].strip()
        if r.get("parent"):
            p = upload.get(str(r["parent"]))
            if p:
                theirs["parent"] = {"key": str(r["parent"]), "name": p["name"], "type": p["type"]}
        for col, v in r.items():
            if col in mo.ENTITY_COLS or v in (None, ""):
                continue
            dt = (dtypes.get(col.lower()) or (None, spec_types.get(col.lower())))[1]
            if dt == "entity_ref":
                p = upload.get(str(v))
                theirs[f"value:{col}"] = {"key": str(v), "name": p["name"] if p else str(v)}
            else:
                theirs[f"value:{col}"] = _norm(v, dt)
        item["theirs"] = theirs
        if target is None:
            continue
        for f, tv in theirs.items():
            if f == "description":
                mv = (target["description"] or "").strip() or None
                same = mv == tv
            elif f == "parent":
                p = upload.get(tv["key"])
                mv = str(target["parent"]) if target["parent"] else None
                same = p is not None and p["match"] is not None and mv == p["match"]
            else:
                code = f[6:].lower()
                mv = target["values"].get(code)
                if isinstance(tv, dict):
                    p = upload.get(tv["key"])
                    same = p is not None and p["match"] is not None and mv == p["match"]
                else:
                    same = mv == tv
            if same:
                continue
            show = tv["name"] if isinstance(tv, dict) else tv
            if mv in (None, ""):
                item["fills"].append({"field": f, "theirs": show})
            else:
                item["conflicts"] += 1
                conflicts.append({"id": f"{item['key']}|{f}", "entity": item["name"], "entity_type": item["entity_type"],
                                  "match": item["match"],
                                  "field": "Description" if f == "description" else "Part of" if f == "parent" else f[6:],
                                  "code": f, "mine": _show_mine(conn, f, mv), "theirs": show})
        if not item["fills"] and not item["conflicts"]:
            item["action"] = "same"
    # relationships: new ones between entities of the merged model
    existing = {(r["type"].lower(), str(r["s"]), str(r["t"])) for r in _rows(conn, """
        SELECT rt.code AS type, s.guid AS s, t.guid AS t FROM core.relationships r
          JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
          JOIN core.entities s ON s.id = r.source_entity_id JOIN core.entities t ON t.id = r.target_entity_id
         WHERE r.model_id = :m AND NOT r.is_deleted""", m=m["_id"])}
    rels, same_rels = [], 0
    for r in pkg["relationships"]:
        s, t = upload.get(str(r.get("source"))), upload.get(str(r.get("target")))
        if not s or not t or not r.get("type"):
            continue
        if s["match"] and t["match"] and (str(r["type"]).lower(), s["match"], t["match"]) in existing:
            same_rels += 1
            continue
        rels.append({"type": r["type"], "source": str(r["source"]), "target": str(r["target"]), "source_name": s["name"],
                     "target_name": t["name"], "name": r.get("name") or ""})
    plan = {"filename": filename, "model": {"id": str(m["id"]), "name": m["name"]}, "with_data": with_data,
            "upload_has_data": has_data,
            "source": (pkg.get("manifest") or {}).get("model", {}).get("name") or filename,
            "metamodel_gaps": gaps, "entities": entities, "conflicts": conflicts, "relationships": rels,
            "counts": {"create": sum(1 for e in entities if e["action"] == "create"),
                       "update": sum(1 for e in entities if e["action"] == "update"),
                       "same": sum(1 for e in entities if e["action"] == "same"),
                       "conflicts": len(conflicts), "relationships": len(rels), "relationships_already_there": same_rels},
            "spec": spec}
    row = _one(conn, """INSERT INTO core.merge_sessions (model_id, author, filename, plan) VALUES (:m, :a, :f, CAST(:p AS jsonb))
                        RETURNING guid""", m=m["_id"], a=user.username.lower(), f=filename or "", p=json.dumps(plan, default=str))
    may_add = perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"])
    return {**{k: v for k, v in plan.items() if k != "spec"}, "id": str(row["guid"]), "may_add_metamodel": may_add}


def _show_mine(conn, field: str, value: Any) -> Any:
    if value and (field == "parent" or (field.startswith("value:") and repo._as_guid(value))):
        e = _one(conn, "SELECT name FROM core.entities WHERE guid = CAST(:g AS uuid)", g=str(value))
        return e["name"] if e else value
    return value


def _session(conn, m: dict, session: Any, user) -> dict:
    g = repo._as_guid(session)
    s = _one(conn, "SELECT * FROM core.merge_sessions WHERE guid = :g AND model_id = :m", g=str(g), m=m["_id"]) if g else None
    if not s:
        raise EditError("No such merge.", 404)
    if s["author"] != user.username.lower():
        raise EditError("Only the person who uploaded it applies a merge.", 403)
    if s["status"] != "open":
        raise EditError(f"This merge was {s['status']} already.", 409)
    return s


def _add_metamodel(conn, m: dict, spec: dict, gaps: dict, user) -> int:
    """Adds the upload's missing entity types, attributes and relationship types to the model's metamodel
    (one new version), keeping everything the model already has as it is."""
    if not (perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"])):
        raise EditError("Adding to the metamodel needs the Model Admin role on this model (leave it out instead).", 403)
    have = mo.metamodel_spec(conn, str(m["id"]))
    merged = json.loads(json.dumps(have, default=str))

    def codes(items, k="code"):
        return {str(i[k]).lower() for i in items}
    for section in ("layers", "pick_lists", "attributes"):
        known = codes(merged[section])
        for item in spec.get(section) or []:
            if str(item["code"]).lower() not in known:
                merged[section].append(item)
    by_type = {t["code"].lower(): t for t in merged["entity_types"]}
    wanted_types = {g["code"].lower() for g in gaps["entity_types"]}
    for t in spec.get("entity_types") or []:
        code = t["code"].lower()
        if code in wanted_types and code not in by_type:
            merged["entity_types"].append(t)
        elif code in by_type:
            mine = codes(by_type[code].get("attributes") or [], "attribute")
            for a in t.get("attributes") or []:
                if a["attribute"].lower() not in mine:
                    by_type[code].setdefault("attributes", []).append(a)
    known = codes(merged["relationship_types"])
    for r in spec.get("relationship_types") or []:
        if r["code"].lower() not in known and r["code"].lower() in {g["code"].lower() for g in gaps["relationship_types"]}:
            merged["relationship_types"].append(r)
    have_allowed = {(a["source"].lower(), a["relationship"].lower(), a["target"].lower()) for a in merged["allowed"]}
    types_now = codes(merged["entity_types"])
    rels_now = codes(merged["relationship_types"])
    for a in spec.get("allowed") or []:
        k = (a["source"].lower(), a["relationship"].lower(), a["target"].lower())
        if k not in have_allowed and k[0] in types_now and k[2] in types_now and k[1] in rels_now:
            merged["allowed"].append(a)
    version = conn.execute(text("SELECT core.publish_metamodel_version(:m, :n)"),
                           {"m": m["_id"], "n": f"Added from a merged model ({user.username})"}).scalar_one()
    mo.apply_spec(conn, m["_id"], merged, "merge")
    from . import reports
    reports.refresh_typed_views(conn)
    return version


def apply(conn, model: Any, session: Any, user, decisions: dict | None = None, all_conflicts: str = "",
          add_metamodel: bool = False) -> dict:
    """Applies a merge: optionally adds the missing metamodel parts (Model Admins), then records the new
    entities, the filled and decided fields and the new relationships as uncommitted changes of the person.
    decisions: {conflict id: "mine" | "theirs" | {"value": text}}; all_conflicts "mine" or "theirs" for the rest."""
    m = repo.get_model(conn, model)
    s = _session(conn, m, session, user)
    plan = cm._json(s["plan"])
    decisions = decisions or {}
    undecided = [c for c in plan["conflicts"] if c["id"] not in decisions and all_conflicts not in ("mine", "theirs")]
    if undecided:
        raise EditError(f"Decide every conflict first ({len(undecided)} left), or take all of the model's or all of the upload's.", 409)
    version = None
    gaps = plan["metamodel_gaps"]
    if not plan.get("with_data", True):   # the metamodel only: it changes at once (the metamodel is not committed)
        if not any(gaps[k] for k in gaps):
            raise EditError("The upload's metamodel has nothing this model lacks: nothing to merge.", 409)
        version = _add_metamodel(conn, m, plan["spec"], gaps, user)
        result = {"recorded": 0, "failed": [], "failed_count": 0, "left_out": {}, "metamodel_version": version,
                  "added": {k: len(v) for k, v in gaps.items()}}
        conn.execute(text("""UPDATE core.merge_sessions SET status = 'applied', applied_at = now(), result = CAST(:r AS jsonb)
                             WHERE id = :i"""), {"r": json.dumps(result, default=str), "i": s["id"]})
        result["note"] = (f"The metamodel now has what the upload's had and this model lacked (metamodel version {version}). "
                          "Metamodel changes apply at once; only content is committed.")
        return result
    if add_metamodel and any(gaps[k] for k in gaps):
        version = _add_metamodel(conn, m, plan["spec"], gaps, user)
    known_types = {r["code"].lower() for r in _rows(conn, "SELECT code FROM core.entity_types WHERE model_id = :m AND NOT is_deleted",
                                                     m=m["_id"])}
    attrs_by_type: dict[str, set[str]] = {}
    for r in _rows(conn, """SELECT t.code AS t, a.code AS a FROM core.item_attributes i JOIN core.entity_types t ON t.id = i.entity_type_id
                             JOIN core.attribute_types a ON a.id = i.attribute_type_id
                            WHERE i.model_id = :m AND NOT i.is_deleted""", m=m["_id"]):
        attrs_by_type.setdefault(r["t"].lower(), set()).add(r["a"].lower())
    rel_types = {r["code"].lower() for r in _rows(conn, "SELECT code FROM core.relationship_types WHERE model_id = :m AND NOT is_deleted",
                                                   m=m["_id"])}
    guid_of: dict[str, str] = {}
    for e in plan["entities"]:
        if e["entity_type"].lower() not in known_types:
            continue
        guid_of[e["key"]] = e["match"] or str(uuid.uuid4())

    def ref(v):
        return guid_of.get(v["key"]) if isinstance(v, dict) else v

    def decide(item, f, theirs):
        d = decisions.get(f"{item['key']}|{f}", all_conflicts or "mine")
        if d == "theirs":
            return True, ref(theirs)
        if isinstance(d, dict) and "value" in d:
            return True, d["value"]
        return False, None
    conflict_ids = {c["id"] for c in plan["conflicts"]}
    items: list[tuple[str, dict]] = []
    updates: list[tuple[str, dict]] = []
    later_parents: list[tuple[str, dict]] = []
    left_out = {"entities": 0, "values": 0, "relationships": 0}
    for e in plan["entities"]:
        t = e["entity_type"].lower()
        if t not in known_types:
            left_out["entities"] += 1
            continue
        allowed = attrs_by_type.get(t, set())
        data: dict[str, Any] = {}
        values: dict[str, Any] = {}
        for f, theirs in e["theirs"].items():
            if f.startswith("value:") and f[6:].lower() not in allowed:
                left_out["values"] += 1
                continue
            if e["action"] == "create":
                use, val = True, ref(theirs)
            elif f"{e['key']}|{f}" in conflict_ids:
                use, val = decide(e, f, theirs)
            elif any(x["field"] == f for x in e["fills"]):
                use, val = True, ref(theirs)
            else:
                use = False
            if not use or val in (None, ""):
                continue
            if f == "parent":
                if e["action"] == "create" and not next((x for x in plan["entities"] if x["key"] == theirs["key"] and x["match"]), None):
                    later_parents.append((guid_of[e["key"]], {"parent": val}))   # a new parent: set once both exist
                else:
                    data["parent"] = val
            elif f == "description":
                data["description"] = val
            else:
                values[f[6:]] = val
        if values:
            data["values"] = values
        if e["action"] == "create":
            items.append(("entity.create", {"data": {"guid": guid_of[e["key"]], "entity_type": e["entity_type"], "name": e["name"],
                                                     **data}}))
        elif data:
            updates.append(("entity.update", {"entity": e["match"], "data": data}))
    # new entities first, then changes to existing ones (which may point at new ones), then new parents
    items += updates + [("entity.update", {"entity": g, "data": d}) for g, d in later_parents]
    for r in plan["relationships"]:
        s_g, t_g = guid_of.get(r["source"]), guid_of.get(r["target"])
        if not s_g or not t_g or str(r["type"]).lower() not in rel_types:
            left_out["relationships"] += 1
            continue
        items.append(("relationship.create", {"data": {"relationship_type": r["type"], "source": s_g, "target": t_g,
                                                       "name": r.get("name") or "", "allow_outside": True}}))
    results = cm.record_many(conn, m["id"], user.username, items) if items else []
    failed = [{"change": op, "what": (a.get("data") or {}).get("name") or a.get("entity"), "error": r["error"]}
              for (op, a), r in zip(items, results, strict=True) if not r["ok"]]
    result = {"recorded": sum(1 for r in results if r["ok"]), "failed": failed[:200], "failed_count": len(failed),
              "left_out": left_out, "metamodel_version": version}
    conn.execute(text("""UPDATE core.merge_sessions SET status = 'applied', applied_at = now(), result = CAST(:r AS jsonb)
                         WHERE id = :i"""), {"r": json.dumps(result, default=str), "i": s["id"]})
    result["note"] = ("The merge is in your uncommitted changes (Changes tab): commit it, or ask for a commit; "
                      "only you see it until then.")
    return result


def cancel(conn, model: Any, session: Any, user) -> dict:
    m = repo.get_model(conn, model)
    s = _session(conn, m, session, user)
    conn.execute(text("UPDATE core.merge_sessions SET status = 'cancelled' WHERE id = :i"), {"i": s["id"]})
    return {"cancelled": str(s["guid"])}


# ---------------------------------------------------------------- a test file to try merging with (laptop and demos)
def _test_value(a: dict, pick_lists: dict, n: int) -> str | None:
    dt = a.get("data_type") or "text"
    if a.get("pick_list") and pick_lists.get(str(a["pick_list"]).lower()):
        values = pick_lists[str(a["pick_list"]).lower()]
        return str(values[n % len(values)])
    if dt in ("text", "long_text"):
        return f"Merge test value {n + 1}"
    if dt in ("integer", "whole_number"):
        return "3"
    if dt in ("number", "decimal", "currency"):
        return str(1000 * (n + 1))
    if dt == "date":
        return f"2027-0{1 + n % 9}-01"
    if dt in ("boolean", "yes_no"):
        return "Yes"
    return None   # references, links and the like: not used for a test value


def sample_package(conn, model: Any, fmt: str = "zip", actor: str | None = None, with_data: bool = True) -> tuple[bytes, str, str]:
    """A package made from this model to try a merge with: the model itself with some descriptions and values
    changed (conflicts), some empty fields filled, four new entities with relationships copied from entities of
    their type, and two attributes the metamodel lacks (offered to a Model Admin to add). Invented names only.
    with_data False: the metamodel only, with the two attributes (to try a merge without data)."""
    m = repo.get_model(conn, model)
    if m["kind"] == "template":
        raise EditError("A root metamodel has no content to merge.", 409)
    spec = json.loads(json.dumps(mo.metamodel_spec(conn, model), default=str))
    content = mo.package_content(conn, model)
    attrs = {a["code"]: a for a in spec.get("attributes") or []}
    pick_lists = {str(p["code"]).lower(): p.get("values") or [] for p in spec.get("pick_lists") or []}
    type_attrs = {t["code"]: [i["attribute"] for i in t.get("attributes") or []] for t in spec.get("entity_types") or []}
    ents = [(code, r) for code, rows in sorted(content["entities"].items()) for r in rows]
    if not ents:
        raise EditError(f"{m['name']} has no content yet: enter some first, or download another model to merge.", 409)
    changed = filled = 0
    tag = uuid.uuid4().hex[:4]   # each file has its own new entities and values, so it can be tried again and again
    # conflicts: a different description, and a different text value, on a few entities
    for code, r in ents[::max(1, len(ents) // 6)][:6]:
        if r.get("description"):
            r["description"] = f"{r['description'].split(' (merge test')[0]} (merge test {tag})"
            changed += 1
        for c in type_attrs.get(code, []):
            a = attrs.get(c) or {}
            if r.get(c) and (a.get("data_type") in ("text", "long_text")) and not a.get("pick_list"):
                r[c] = f"{str(r[c]).split(' (merge test')[0]} (merge test {tag})"
                changed += 1
                break
    # fills: values for fields the model leaves empty
    for code, r in ents[1::max(1, len(ents) // 8)][:8]:
        for c in type_attrs.get(code, []):
            if not r.get(c):
                v = _test_value(attrs.get(c) or {}, pick_lists, filled)
                if v is not None:
                    r[c] = v
                    filled += 1
                    break
    # new entities, each with the relationships of an entity of its type
    by_source: dict[str, list[dict]] = {}
    for rel in content["relationships"]:
        by_source.setdefault(str(rel["source"]), []).append(rel)
    picks = [(code, r) for code, r in ents if by_source.get(str(r["key"]))][:: max(1, len(ents) // 4)][:4]
    for i, (code, r) in enumerate(picks, 1):
        key = str(uuid.uuid4())
        new = {k: v for k, v in r.items()}
        new.update(key=key, display_id="", name=f"Merge test {tag} {r['name'].split(' (')[0]} {i}", parent="",
                   description=f"A new {code} from the merge test file, modelled on {r['name']}")
        content["entities"][code].append(new)
        for rel in by_source[str(r["key"])][:3]:
            content["relationships"].append({**rel, "key": str(uuid.uuid4()), "source": key})
    # two attributes the metamodel lacks (new each time), on the types of the first new entities
    text_attr = next((a for a in spec.get("attributes") or [] if a.get("data_type") == "text" and not a.get("pick_list")), None)
    for n, (code, _r) in enumerate(picks[:2], 1):
        item = next((i for t in spec["entity_types"] if t["code"] == code for i in t.get("attributes") or []), None)
        if not (text_attr and item):
            continue
        acode = f"MergeTest{tag}{n}"
        spec["attributes"].append({**text_attr, "code": acode, "name": f"Merge test note {tag} {n}",
                                   "description": "An attribute only the merge test file has"})
        for t in spec["entity_types"]:
            if t["code"] == code:
                t.setdefault("attributes", []).append({**item, "attribute": acode, "required": False, "default": None})
        for r in content["entities"][code]:
            if str(r["name"]).startswith(f"Merge test {tag} "):
                r[acode] = "Added by the merge test file"
    if not with_data:   # the metamodel only, with what the test adds to it
        content = {"entities": {}, "relationships": []}
    manifest = mo._manifest(conn, m, spec, content, actor)
    manifest["model"]["name"] = f"{m['name']} (merge test file{'' if with_data else ', metamodel only'})"
    manifest["merge_test"] = {"conflicts": changed, "fills": filled, "new_entities": len(picks)}
    base = re.sub(r"[^A-Za-z0-9._]+", "-", f"{m['name']} merge test{'' if with_data else ' metamodel'}").strip("-")
    return mo.write_package(manifest, spec, content, None, fmt, base)
