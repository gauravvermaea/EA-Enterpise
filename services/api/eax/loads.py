"""Loading sheets (build phase 10.1, D78, D197): an uploaded workbook or CSV becomes the uploader's own uncommitted
changes (D165), after a preview.

    create(conn, model, user, file_name, content, kind)  the load, kept with its file
    preview(conn, load)                                   what each row would do: new, changed, unchanged, delete, problem
    edit_row(conn, user, load, n, values)                 correct a row on screen; the preview is worked out again
    add(conn, user, load)                                 the rows become the owner's uncommitted changes (record_many)
    undo(conn, user, load)                                its changes discarded (uncommitted) or rolled back (committed)

Matching (D197): a row is found by its GUID, then by its ID (display ID); a row with neither (a sheet from another
system, a feed) is found by type and name when exactly one entity has that name; otherwise (or with a provisional
NEW-... ID) it is new. The preview says how each row was matched. Relationships give their ends by ID (or GUID); an end that is a new row of the same load is
found by its provisional ID; an end not found is a problem, loaded once the entity has an ID (load again).
Sheets from other systems are mapped first: each header to a field or attribute (a mapping can be saved and reused).
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from . import audit
from . import commits as cm
from . import permissions as perms
from . import repository as repo
from . import sheets as sh
from .metamodel_edit import EditError

YES = {"yes", "y", "true", "1", "x", "delete"}
ENTITY_FIELDS = ("name", "description", "parent", "tags")
MAX_ROWS = 20000


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def _one(conn, sql: str, **p) -> dict | None:
    r = _rows(conn, sql, **p)
    return r[0] if r else None


def _bytes(v: Any) -> bytes:
    if isinstance(v, str) and v.startswith("\\x"):   # a driver that answers bytea as text
        return bytes.fromhex(v[2:])
    return bytes(v)


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def _may_load(conn, user, m: dict) -> None:
    if perms.SUPER_ADMIN in user.roles:
        return
    if not set(perms.model_roles(conn, user.username, m["id"])) & set(perms.MODEL_PERMISSIONS["model.content"]):
        raise EditError(f"Loading sheets into {m['name']} needs a role that changes its content (Architect, Committer, "
                        "Model Sub Admin or Model Admin).", 403)


def _may_manage(conn, user, m: dict, what: str) -> None:
    if perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"]):
        return
    raise EditError(f"{what} on {m['name']} needs the Model Admin role.", 403)


# ---------------------------------------------------------------- loads
def create(conn, model: Any, user, file_name: str, content: bytes) -> dict:
    m = repo.get_model(conn, model)
    _may_load(conn, user, m)
    if not content:
        raise EditError("The file is empty.")
    sh.read(content, file_name)   # readable at all: say so now, not in the background
    fmt = (file_name.rsplit(".", 1)[-1] if "." in file_name else "csv").lower()
    row = _one(conn, """INSERT INTO core.loads (model_id, file_name, format, content, owner, created_by)
                        VALUES (:m, :f, :fmt, :c, :o, :u) RETURNING guid""",
               m=m["_id"], f=file_name[:200], fmt=fmt, c=content, o=user.username.lower(), u=user.username.lower())
    return get(conn, user, str(row["guid"]), with_rows=False)


def _load(conn, load: Any) -> dict:
    g = repo._as_guid(load)
    r = _one(conn, "SELECT l.*, m.guid AS model_guid, m.name AS model_name FROM core.loads l JOIN core.models m ON m.id = l.model_id "
                   "WHERE l.guid = CAST(:g AS uuid)", g=str(g)) if g else None
    if not r:
        raise EditError("No such load.", 404)
    for k in ("preview", "summary", "mapping"):
        r[k] = _j(r[k]) or {}
    return r


def _out(r: dict, with_rows: bool = True, row_filter: str = "", limit: int = 2000) -> dict:
    p = r["preview"] or {}
    rows = p.get("rows", [])
    if row_filter:
        rows = [x for x in rows if x["action"] == row_filter]
    out = {"id": str(r["guid"]), "model": {"id": str(r["model_guid"]), "name": r["model_name"]},
           "file_name": r["file_name"], "format": r["format"], "status": r["status"], "message": r["message"],
           "owner": r["owner"], "created_by": r["created_by"], "created_at": r["created_at"], "added_at": r["added_at"],
           "undone_at": r["undone_at"], "undone_by": r["undone_by"], "summary": r["summary"], "changes": len(r["change_ids"] or []),
           "sheets": p.get("sheets", []), "needs_mapping": p.get("needs_mapping", []), "blank_clears": p.get("blank_clears", True)}
    if with_rows:
        out["rows"] = rows[:limit]
        out["rows_total"] = len(rows)
    return out


def get(conn, user, load: Any, with_rows: bool = True, row_filter: str = "") -> dict:
    r = _load(conn, load)
    if r["created_by"] != user.username.lower() and r["owner"] != user.username.lower() and perms.SUPER_ADMIN not in user.roles:
        roles = set(perms.model_roles(conn, user.username, str(r["model_guid"])))
        if not roles & {perms.MODEL_ADMIN, perms.MODEL_SUB_ADMIN, perms.COMMITTER}:
            raise EditError("No such load.", 404)
    return _out(r, with_rows, row_filter)


def list_loads(conn, user, model: Any) -> dict:
    m = repo.get_model(conn, model)
    rows = _rows(conn, """SELECT l.*, m.guid AS model_guid, m.name AS model_name FROM core.loads l JOIN core.models m ON m.id = l.model_id
                           WHERE l.model_id = :m ORDER BY l.created_at DESC LIMIT 200""", m=m["_id"])
    admin = perms.SUPER_ADMIN in user.roles or set(perms.model_roles(conn, user.username, m["id"])) & {
        perms.MODEL_ADMIN, perms.MODEL_SUB_ADMIN, perms.COMMITTER}
    out = []
    for r in rows:
        if admin or user.username.lower() in (r["created_by"], r["owner"]):
            for k in ("preview", "summary", "mapping"):
                r[k] = _j(r[k]) or {}
            out.append(_out(r, with_rows=False))
    return {"loads": out}


# ---------------------------------------------------------------- working out what each row does
def _norm(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _same(a: str, b: str, data_type: str = "text") -> bool:
    a, b = _norm(a), _norm(b)
    if a == b:
        return True
    if data_type in ("integer", "decimal", "currency", "percent"):
        try:
            return Decimal(a.replace(",", ".") or "0") == Decimal(b.replace(",", ".") or "0") and bool(a) == bool(b)
        except InvalidOperation:
            return False
    if data_type == "boolean":
        return _bool(a) == _bool(b) and _bool(a) is not None
    if data_type == "date":
        return a[:10] == b[:10]
    return False


def _bool(v: str) -> bool | None:
    s = _norm(v).lower()
    return True if s in ("yes", "y", "true", "1") else False if s in ("no", "n", "false", "0") else None


def _check_value(a: dict, v: str) -> str | None:
    """A value that cannot be stored as its data type: the row is a problem until it is corrected."""
    if not v:
        return None
    t = a["data_type"]
    if t in ("integer", "decimal", "currency", "percent"):
        try:
            d = Decimal(v.replace(" ", "").replace(",", "."))
            if t == "integer" and d != d.to_integral_value():
                return f"{a['name']}: {v!r} is not a whole number"
        except InvalidOperation:
            return f"{a['name']}: {v!r} is not a number"
    elif t == "date":
        try:
            dt.date.fromisoformat(v[:10])
        except ValueError:
            return f"{a['name']}: {v!r} is not a date (YYYY-MM-DD)"
    elif t == "boolean" and _bool(v) is None:
        return f"{a['name']}: {v!r} is not Yes or No"
    return None


def _type_for(sheet: dict, types: list[dict], meta: dict) -> dict | None:
    name = sheet["name"].strip().lower()
    for t in types:
        if name in (t["code"].lower(), t["name"].lower(), t["name"][:31].lower(), sh.sheet_name(t["name"], set()).lower()):
            return t
    return None


def _is_relationships(sheet: dict) -> bool:
    codes = set(sheet["codes"])
    return sheet["name"].lower() in ("relationships", "relationship") or {"source", "target"} <= codes


def preview(conn, load: Any, user=None) -> dict:
    """Works out (and keeps) what every row of the load would do. Run as a background task (D192)."""
    r = _load(conn, load)
    m = repo.get_model(conn, str(r["model_guid"]))
    stored = r["preview"] or {}
    if stored.get("input"):
        parsed = stored["input"]
    else:
        parsed = sh.read(_bytes(r["content"]), r["file_name"])
        if sum(len(s["rows"]) for s in parsed["sheets"]) > MAX_ROWS:
            raise EditError(f"At most {MAX_ROWS:,} rows a load: split the file.")
    blank_clears = stored.get("blank_clears", True)
    mapping = r["mapping"] or {}
    _, all_types = sh.types_of(conn, str(m["id"]), [t["code"] for t in _rows(conn, """SELECT code FROM core.entity_types
                                                                                   WHERE model_id = :m AND NOT is_deleted""", m=m["_id"])])
    types_by_code = {t["code"].lower(): t for t in all_types}

    # which sheet is which type; sheets from other systems through their mapping
    plan, needs = [], []
    for s in parsed["sheets"]:
        if _is_relationships(s) and s.get("ours", True):
            plan.append(("rel", s, None, None))
            continue
        mp = mapping.get(s["name"])
        t = None
        if mp and mp.get("entity_type"):
            t = types_by_code.get(str(mp["entity_type"]).lower()) or next(
                (x for x in all_types if x["name"].lower() == str(mp["entity_type"]).lower()), None)
        if t is None and s.get("ours"):
            t = _type_for(s, all_types, parsed.get("meta") or {})
        cols = None
        if mp and mp.get("columns"):
            cols = {h: c for h, c in mp["columns"].items() if c}
        elif s.get("ours"):
            cols = {c: c for c in s["codes"]}
        if mp and mp.get("relationships"):
            plan.append(("rel", s, None, cols))
            continue
        if t is None or cols is None:
            needs.append({"sheet": s["name"], "headers": s["headers"], "rows": len(s["rows"]),
                          "type_guess": (t or {}).get("code"), "sample": [{k: v for k, v in x.items() if k != "_row"} for x in s["rows"][:3]]})
            continue
        plan.append(("ent", s, t, cols))
    if needs:
        p = {"input": parsed, "needs_mapping": needs, "rows": [], "sheets": [], "blank_clears": blank_clears}
        _save_preview(conn, r["id"], "mapping", p, {"needs_mapping": len(needs)}, "Map the columns of the sheets EA Explorer does not know.")
        return {"status": "mapping", "needs_mapping": needs}

    # what is in the model now, for the types in the load
    chosen = [t for kind, s, t, c in plan if kind == "ent"]
    current, cur_rels, _ = sh.content_of(conn, m, list({t["_id"]: t for t in chosen}.values()) or all_types[:0])
    by_guid, by_did, by_name = {}, {}, {}
    for t in chosen:
        for e in current.get(t["_id"], []):
            by_guid[e["guid"].lower()] = (t, e)
            by_did[(e["display_id"] or "").lower()] = (t, e)
            by_name.setdefault((t["code"], (e["name"] or "").strip().lower()), []).append((t, e))
    any_did = {(x["display_id"] or "").lower(): str(x["guid"]) for x in _rows(conn, """SELECT guid, display_id FROM core.entities
                                                                                 WHERE model_id = :m AND NOT is_deleted""", m=m["_id"])}
    any_guid = set(any_did.values())
    rules = {t["_id"]: repo._rules_for_type(conn, m["_id"], t["_id"]) for t in chosen}
    from . import rules as rule_check

    rows: list[dict] = []
    provisional: dict[str, str] = {}   # NEW-... (or a row's own ID) -> the guid the new entity will get
    sheets_out = []
    n = 0
    for kind, s, t, cols in plan:
        if kind != "ent":
            continue
        attrs = {a["code"]: a for a in t["attributes"]}
        counts = {"new": 0, "changed": 0, "unchanged": 0, "delete": 0, "problem": 0}
        for raw in s["rows"]:
            n += 1
            d = {cols[h]: _norm(v) for h, v in raw.items() if h in cols}
            did = d.get("display_id", "")
            if did == "=NEW":
                did = f"NEW-{s.get('new_prefix') or t['code'][:3].upper()}-{raw['_row'] - 2:04d}"
            g = (d.get("guid") or "").lower()
            match = by_guid.get(g) if g else None
            if match is None and did and not did.upper().startswith("NEW-"):
                match = by_did.get(did.lower())
            by = "guid" if match and g else "id" if match else None
            if match is None and not g and d.get("name"):   # no GUID and no known ID: the one entity of this type with this name
                same = by_name.get((t["code"], d["name"].strip().lower()), [])
                if len(same) == 1:
                    match, by = same[0], "name"
            delete = _norm(d.get("delete")).lower() in YES
            row = {"n": n, "sheet": s["name"], "row": raw["_row"], "kind": "entity", "entity_type": t["code"],
                   "entity_type_name": t["name"], "id": did, "guid": g or None, "name": d.get("name", ""), "matched_by": by,
                   "changes": [], "problems": [], "warnings": [], "data": d}
            if g and match is None and g in any_guid:
                row["problems"].append("This GUID belongs to an entity of another type or sheet.")
            if match is None:
                if delete:
                    row["action"] = "problem" if (g or did) else "unchanged"
                    if g or did:
                        row["problems"].append("Marked for deletion but not found in the model.")
                elif not d.get("name"):
                    row["action"] = "problem"
                    row["problems"].append("A new row needs a name.")
                else:
                    row["action"] = "new"
                    new_guid = g if g and g not in any_guid else str(uuid.uuid4())
                    row["guid"] = new_guid
                    if did:
                        provisional[did.lower()] = new_guid
                    provisional[d["name"].lower() + "|" + t["code"].lower()] = new_guid
                    for code in ENTITY_FIELDS:
                        if d.get(code):
                            row["changes"].append({"field": code, "old": "", "new": d[code]})
                    for code, a in attrs.items():
                        if d.get(code):
                            row["changes"].append({"field": a["name"], "code": code, "old": "", "new": d[code]})
            else:
                _t, e = match
                row["guid"], row["id"] = e["guid"], e["display_id"]
                if delete:
                    row["action"] = "delete"
                else:
                    for code in ENTITY_FIELDS:
                        if code in d and not _same(d[code], e.get(code, "")) and (d[code] or blank_clears):
                            if code == "tags" and {x.strip().lower() for x in d[code].split(",") if x.strip()} == \
                                    {x.strip().lower() for x in (e.get("tags") or "").split(",") if x.strip()}:
                                continue
                            if code == "name" and not d[code]:
                                row["problems"].append("The name cannot be empty.")
                                continue
                            row["changes"].append({"field": code, "old": e.get(code, ""), "new": d[code]})
                    for code, a in attrs.items():
                        if code in d and not _same(d[code], e.get(code, ""), a["data_type"]) and (d[code] or blank_clears):
                            row["changes"].append({"field": a["name"], "code": code, "old": e.get(code, ""), "new": d[code]})
                    row["action"] = "changed" if row["changes"] else "unchanged"
            for code, a in attrs.items():
                if d.get(code):
                    p_ = _check_value(a, d[code])
                    if p_:
                        row["problems"].append(p_)
                    elif a["pick_list_values"] and d[code] not in a["pick_list_values"]:
                        row["warnings"].append(f"{a['name']}: {d[code]!r} is not one of the pick list values")
            if row["action"] in ("new", "changed") and not row["problems"]:
                ent = {"name": d.get("name") or (match[1]["name"] if match else ""), "description": d.get("description", ""),
                       "display_id": row["id"], "relationships": []}
                vals = []
                for code, a in attrs.items():
                    v = d[code] if code in d else (match[1].get(code, "") if match else "")
                    vals.append({**a, "value": v or None})
                for w in rule_check.evaluate(ent, vals, rules[t["_id"]]):
                    row["warnings"].append(f"{w['field']}: {w['message']}")
            if row["problems"]:
                row["action"] = "problem"
            counts[row["action"]] += 1
            rows.append(row)
        sheets_out.append({"sheet": s["name"], "kind": "entities", "entity_type": t["code"], "entity_type_name": t["name"],
                           "rows": len(s["rows"]), **counts})

    # relationships: ends by ID or GUID, existing or new in this load
    rt_rows = _rows(conn, "SELECT id, guid, code, name FROM core.relationship_types WHERE model_id = :m AND NOT is_deleted", m=m["_id"])
    rts = {x["name"].lower(): x for x in rt_rows} | {x["code"].lower(): x for x in rt_rows}
    ent_types = {str(x["guid"]): x["t"] for x in _rows(conn, """SELECT guid, entity_type_id AS t FROM core.entities
                                                                  WHERE model_id = :m AND NOT is_deleted""", m=m["_id"])}
    for row in rows:
        if row["action"] == "new":
            ent_types[row["guid"]] = next(t["_id"] for t in chosen if t["code"] == row["entity_type"])
    allowed = {(a["r"], a["s"], a["t"]) for a in _rows(conn, """SELECT relationship_type_id AS r, source_type_id AS s, target_type_id AS t
                                                                 FROM core.allowed_relationships WHERE model_id = :m AND NOT is_deleted""",
                                                       m=m["_id"])}
    existing = {(x["source"], x["rt"], x["target"]): x for x in _rows(conn, """
        SELECT r.guid::text AS guid, s.guid::text AS source, r.relationship_type_id AS rt, t.guid::text AS target, r.name
          FROM core.relationships r JOIN core.entities s ON s.id = r.source_entity_id JOIN core.entities t ON t.id = r.target_entity_id
         WHERE r.model_id = :m AND NOT r.is_deleted""", m=m["_id"])}
    by_rel_guid = {x["guid"]: x for x in existing.values()}

    def end(v: str) -> str | None:
        v = _norm(v)
        if not v:
            return None
        if v.lower() in provisional:
            return provisional[v.lower()]
        g = repo._as_guid(v)
        if g and str(g) in ent_types:
            return str(g)
        return any_did.get(v.lower())
    for kind, s, _t, cols in plan:
        if kind != "rel":
            continue
        counts = {"new": 0, "changed": 0, "unchanged": 0, "delete": 0, "problem": 0}
        cols = cols or {c: c for c in s["codes"]}
        for raw in s["rows"]:
            n += 1
            d = {cols[h]: _norm(v) for h, v in raw.items() if h in cols}
            if not any(d.get(k) for k in ("guid", "source", "target", "relationship_type")):
                continue
            row = {"n": n, "sheet": s["name"], "row": raw["_row"], "kind": "relationship", "guid": (d.get("guid") or "").lower() or None,
                   "source": d.get("source", ""), "relationship_type": d.get("relationship_type", ""), "target": d.get("target", ""),
                   "name": d.get("name", ""), "changes": [], "problems": [], "warnings": [], "data": d}
            delete = _norm(d.get("delete")).lower() in YES
            cur = by_rel_guid.get(row["guid"]) if row["guid"] else None
            src, tgt = end(d.get("source", "")), end(d.get("target", ""))
            rt = rts.get(_norm(d.get("relationship_type")).lower())
            if cur is None and src and tgt and rt:
                cur = existing.get((src, rt["id"], tgt))
                if cur:
                    row["guid"] = cur["guid"]
            if delete:
                row["action"] = "delete" if cur else "problem"
                if not cur:
                    row["problems"].append("Marked for removal but not found in the model.")
            elif cur is not None and (not src or not tgt or not rt or (src, rt["id"], tgt) == (cur["source"], cur["rt"], cur["target"])):
                if d.get("name", cur["name"] or "") != (cur["name"] or "") and "name" in d and (d["name"] or blank_clears):
                    row["action"] = "changed"
                    row["changes"].append({"field": "name", "old": cur["name"] or "", "new": d["name"]})
                else:
                    row["action"] = "unchanged"
            else:
                if not src:
                    row["problems"].append(f"Source {d.get('source') or '(empty)'} not found: load its entity first, then load again.")
                if not tgt:
                    row["problems"].append(f"Target {d.get('target') or '(empty)'} not found: load its entity first, then load again.")
                if not rt:
                    row["problems"].append(f"No relationship type {d.get('relationship_type') or '(empty)'} in this model.")
                if src and tgt and rt and (rt["id"], ent_types.get(src), ent_types.get(tgt)) not in allowed:
                    row["problems"].append(f"The metamodel does not allow {rt['name']} between these types.")
                row["action"] = "problem" if row["problems"] else ("changed" if cur else "new")
                if cur and not row["problems"]:   # same guid, different ends: replaced
                    row["changes"].append({"field": "ends", "old": "", "new": f"{d.get('source')} -> {d.get('target')}"})
            row["_ends"] = [src, rt["code"] if rt else None, tgt]
            counts[row["action"]] += 1
            rows.append(row)
        sheets_out.append({"sheet": s["name"], "kind": "relationships", "rows": len(s["rows"]), **counts})

    summary = {k: sum(1 for x in rows if x["action"] == k) for k in ("new", "changed", "unchanged", "delete", "problem")}
    summary["warnings"] = sum(1 for x in rows if x["warnings"])
    p = {"input": parsed, "rows": rows, "sheets": sheets_out, "needs_mapping": [], "blank_clears": blank_clears}
    msg = (f"{summary['new']} new, {summary['changed']} changed, {summary['delete']} to delete, {summary['unchanged']} unchanged, "
           f"{summary['problem']} with problems.")
    _save_preview(conn, r["id"], "previewed", p, summary, msg)
    return {"status": "previewed", "summary": summary, "message": msg}


def _save_preview(conn, load_id: int, status: str, p: dict, summary: dict, message: str) -> None:
    from sqlalchemy import text
    conn.execute(text("""UPDATE core.loads SET status = :s, preview = CAST(:p AS jsonb), summary = CAST(:sum AS jsonb), message = :msg
                          WHERE id = :i"""), {"s": status, "p": json.dumps(p, default=str), "sum": json.dumps(summary),
                                               "msg": message, "i": load_id})


def set_mapping(conn, user, load: Any, mapping: dict, save_as: str | None = None) -> dict:
    """The columns of sheets EA Explorer does not know: {sheet: {entity_type, columns {header: code or ""}}} (or
    {relationships: true, columns}). Optionally saved as a named mapping for the next file."""
    r = _load(conn, load)
    if r["status"] in ("added", "undone"):
        raise EditError("This load is already added.", 409)
    m = repo.get_model(conn, str(r["model_guid"]))
    merged = {**(r["mapping"] or {}), **(mapping or {})}
    from sqlalchemy import text
    conn.execute(text("UPDATE core.loads SET mapping = CAST(:mp AS jsonb), status = 'uploaded' WHERE id = :i"),
                 {"mp": json.dumps(merged), "i": r["id"]})
    if save_as:
        for sheet, mp in (mapping or {}).items():
            t = repo._find_type(conn, m["_id"], mp["entity_type"]) if mp.get("entity_type") else None
            name = save_as if len(mapping) == 1 else f"{save_as}: {sheet}"
            save_mapping(conn, user, str(m["id"]), name, (t or {}).get("code"), mp.get("columns") or {})
    return {"mapping": merged}


def edit_row(conn, user, load: Any, n: int, values: dict) -> dict:
    """Corrects one row on screen before it is added; the preview is worked out again."""
    r = _load(conn, load)
    if r["status"] in ("added", "undone"):
        raise EditError("This load is already added: change the entities instead.", 409)
    if user.username.lower() not in (r["created_by"], r["owner"]) and perms.SUPER_ADMIN not in user.roles:
        raise EditError("Only the person who loaded it corrects its rows.", 403)
    p = r["preview"]
    target = next((x for x in p.get("rows", []) if x["n"] == int(n)), None)
    if not target:
        raise EditError("No such row.", 404)
    for s in p["input"]["sheets"]:
        if s["name"] == target["sheet"]:
            for raw in s["rows"]:
                if raw["_row"] == target["row"]:
                    mp = (r["mapping"] or {}).get(s["name"], {}).get("columns")
                    back = {v: k for k, v in mp.items()} if mp else {}
                    for code, v in (values or {}).items():
                        raw[back.get(code, code)] = "" if v is None else str(v)
    _save_preview(conn, r["id"], r["status"], p, r["summary"], r["message"])
    preview(conn, str(r["guid"]))
    return get(conn, user, str(r["guid"]))


def add(conn, user, load: Any) -> dict:
    """The previewed rows (not unchanged, not problems) become the owner's uncommitted changes; parents and
    relationship ends that are new rows are created first. Run as a background task (D192)."""
    r = _load(conn, load)
    if r["status"] != "previewed":
        raise EditError("Preview the load first." if r["status"] != "added" else "This load is already added.", 409)
    m = cm._model(conn, str(r["model_guid"]))
    rows = [x for x in r["preview"].get("rows", []) if x["action"] in ("new", "changed", "delete")]
    ops: list[tuple[str, dict]] = []
    owners: list[int] = []
    later: list[tuple[str, dict, int]] = []
    for x in [x for x in rows if x["kind"] == "entity"]:
        d = x["data"]
        if x["action"] == "delete":
            later.append(("entity.delete", {"entity": x["guid"]}, x["n"]))
            continue
        data = {k: d[k] for k in ENTITY_FIELDS if k in d and (d[k] or r["preview"].get("blank_clears", True))}
        values = {c["code"]: c["new"] for c in x["changes"] if c.get("code")}
        if x["action"] == "new":
            data = {**{k: d[k] for k in ENTITY_FIELDS if d.get(k)}, "guid": x["guid"], "entity_type": x["entity_type"], "values": values}
        else:
            data = {k: v for k, v in data.items() if any(c["field"] == k for c in x["changes"])}
            if values:
                data["values"] = values
        parent = data.pop("parent", None) if data.get("parent") else None
        if x["action"] == "new" or data:
            ops.append(("entity.create" if x["action"] == "new" else "entity.update",
                        {"data": data} if x["action"] == "new" else {"entity": x["guid"], "data": data}))
            owners.append(x["n"])
        if parent:   # set after every new entity exists (a parent may be a new row of this load)
            prov = {y["id"].lower(): y["guid"] for y in rows if y["kind"] == "entity" and y["action"] == "new" and y.get("id")}
            later.append(("entity.update", {"entity": x["guid"], "data": {"parent": prov.get(parent.lower(), parent)}}, x["n"]))
    for x in [x for x in rows if x["kind"] == "relationship"]:
        src, rt, tgt = x.get("_ends") or [None, None, None]
        if x["action"] == "delete":
            later.append(("relationship.delete", {"relationship": x["guid"]}, x["n"]))
        elif x["action"] == "new":
            later.append(("relationship.create", {"data": {"relationship_type": rt, "source": src, "target": tgt,
                                                           "name": x["data"].get("name", "")}}, x["n"]))
        elif x["action"] == "changed" and any(c["field"] == "name" for c in x["changes"]):
            later.append(("relationship.rename", {"relationship": x["guid"], "name": x["data"].get("name", "")}, x["n"]))
        elif x["action"] == "changed":
            later.append(("relationship.create", {"data": {"relationship_type": rt, "source": src, "target": tgt,
                                                           "name": x["data"].get("name", "")}}, x["n"]))
            later.append(("relationship.delete", {"relationship": x["guid"]}, x["n"]))
    deletes = [y for y in later if y[0] == "entity.delete"]
    later = [y for y in later if y[0] != "entity.delete"] + deletes   # relationships first, deletes last
    ops += [(op, a) for op, a, _ in later]
    owners += [n for _, _, n in later]
    if not ops:
        raise EditError("Nothing to add: every row is unchanged or has a problem.", 409)
    failed = []
    change_ids = []
    if cm.uses_commits(m):
        results = cm.record_many(conn, str(m["id"]), r["owner"], ops)
        for (op, _a), res, n in zip(ops, results, owners, strict=True):
            if res["ok"]:
                if res.get("kept"):
                    change_ids.append(res["kept"]["change"])
            else:
                failed.append({"n": n, "op": op, "error": res["error"]})
    else:   # a library model being built: no commits, saved at once
        for (op, a), n in zip(ops, owners, strict=True):
            sp = conn.begin_nested()
            try:
                cm._apply(conn, m, op, cm._resolve_refs(conn, m, op, cm._prepare(op, a)), r["owner"])
                sp.commit()
            except (EditError, repo.NotFound) as exc:
                sp.rollback()
                failed.append({"n": n, "op": op, "error": str(exc)})
    from sqlalchemy import text
    source = f"Load of {r['file_name']}"
    if change_ids:   # each change says it came from this load (Changes tab; History once committed)
        conn.execute(text("UPDATE core.pending_changes SET source = :s WHERE guid = ANY (CAST(:c AS uuid[]))"),
                     {"s": source, "c": change_ids})
    # the load itself is one entry in the audit trail and the change log: who loaded which file into which model
    audit.record(conn, actor=getattr(user, "username", str(user)), action="load.added", object_type="model",
                 object_id=str(r["model_guid"]), details={"name": r["file_name"], "changes": len(ops) - len(failed),
                                                          "could_not_be_made": len(failed), "load": str(r["guid"])})
    msg = (f"Added {len(ops) - len(failed)} changes" + (f" ({len(failed)} could not be made)" if failed else "")
           + (": they are your uncommitted changes; commit them (or ask for a commit) on the Changes tab." if cm.uses_commits(m)
              else ": saved."))
    summary = {**r["summary"], "added": len(ops) - len(failed), "failed": failed[:200]}
    conn.execute(text("""UPDATE core.loads SET status = 'added', added_at = now(), change_ids = CAST(:c AS uuid[]),
                                summary = CAST(:s AS jsonb), message = :msg WHERE id = :i"""),
                 {"c": change_ids, "s": json.dumps(summary, default=str), "msg": msg, "i": r["id"]})
    return {"added": len(ops) - len(failed), "failed": failed, "message": msg, "changes": len(change_ids)}


def undo(conn, user, load: Any, force: bool = False) -> dict:
    """Undoes a load: its changes not yet committed are discarded; those committed are rolled back as a new commit
    (committers). Says what was done."""
    r = _load(conn, load)
    if r["status"] != "added":
        raise EditError("Only an added load can be undone.", 409)
    m = cm._model(conn, str(r["model_guid"]))
    ids = [str(x) for x in (r["change_ids"] or [])]
    if isinstance(r["change_ids"], str):   # a driver that answers arrays as text
        ids = [x for x in r["change_ids"].strip("{}").split(",") if x]
    pend = _rows(conn, "SELECT guid, author FROM core.pending_changes WHERE guid = ANY (CAST(:i AS uuid[])) AND status = 'pending'",
                 i=ids) if ids else []
    discarded = rolled = 0
    if pend:
        owner = perms.Principal(r["owner"], ())
        if user.username.lower() != r["owner"] and perms.SUPER_ADMIN not in user.roles:
            raise EditError(f"The changes of this load are {r['owner']}'s uncommitted changes: only they discard them.", 403)
        discarded = cm.discard(conn, str(m["id"]), owner if user.username.lower() != r["owner"] else user,
                               None, [str(p["guid"]) for p in pend])["discarded"]
    items = _rows(conn, """SELECT ci.id, c.guid FROM core.commit_items ci JOIN core.commits c ON c.id = ci.commit_id
                            JOIN core.pending_changes pc ON pc.id = ci.change_id
                            WHERE pc.guid = ANY (CAST(:i AS uuid[])) AND ci.rolled_back_by IS NULL""", i=ids) if ids else []
    by_commit: dict[str, list[int]] = {}
    for it in items:
        by_commit.setdefault(str(it["guid"]), []).append(it["id"])
    for cg, item_ids in by_commit.items():
        cm.roll_back_commit(conn, str(m["id"]), user, cg, item_ids, force, f"Undo of the load {r['file_name']}")
        rolled += len(item_ids)
    from sqlalchemy import text
    msg = f"Undone: {discarded} uncommitted changes discarded, {rolled} committed changes rolled back."
    conn.execute(text("UPDATE core.loads SET status = 'undone', undone_at = now(), undone_by = :u, message = :msg WHERE id = :i"),
                 {"u": user.username.lower(), "msg": msg, "i": r["id"]})
    return {"discarded": discarded, "rolled_back": rolled, "message": msg}


# ---------------------------------------------------------------- column mappings
def list_mappings(conn, model: Any) -> dict:
    m = repo.get_model(conn, model)
    rows = _rows(conn, """SELECT c.guid, c.name, c.columns, t.code AS entity_type, t.name AS entity_type_name, c.created_by, c.created_at
                            FROM core.column_mappings c LEFT JOIN core.entity_types t ON t.id = c.entity_type_id
                           WHERE c.model_id = :m ORDER BY c.name""", m=m["_id"])
    for r in rows:
        r["id"], r["columns"] = str(r.pop("guid")), _j(r["columns"])
    return {"mappings": rows}


def save_mapping(conn, user, model: Any, name: str, entity_type: str | None, columns: dict) -> dict:
    m = repo.get_model(conn, model)
    _may_load(conn, user, m)
    if not (name or "").strip():
        raise EditError("Give the mapping a name.")
    t = repo._find_type(conn, m["_id"], entity_type) if entity_type else None
    row = _one(conn, """INSERT INTO core.column_mappings (model_id, name, entity_type_id, columns, created_by)
                        VALUES (:m, :n, :t, CAST(:c AS jsonb), :u)
                        ON CONFLICT (model_id, lower(name)) DO UPDATE SET columns = EXCLUDED.columns, entity_type_id = EXCLUDED.entity_type_id
                        RETURNING guid""", m=m["_id"], n=name.strip(), t=(t or {}).get("_id"), c=json.dumps(columns), u=user.username.lower())
    return {"id": str(row["guid"]), "name": name.strip()}


def delete_mapping(conn, user, model: Any, mapping: Any) -> dict:
    m = repo.get_model(conn, model)
    _may_load(conn, user, m)
    g = repo._as_guid(mapping)
    from sqlalchemy import text
    n = conn.execute(text("DELETE FROM core.column_mappings WHERE guid = CAST(:g AS uuid) AND model_id = :m"),
                     {"g": str(g), "m": m["_id"]}).rowcount if g else 0
    if not n:
        raise EditError("No such mapping.", 404)
    return {"deleted": str(g)}


def apply_saved_mapping(conn, load: Any, mapping: Any, sheet: str) -> dict:
    """Uses a saved mapping for one sheet of a load."""
    g = repo._as_guid(mapping)
    mp = _one(conn, """SELECT c.columns, t.code FROM core.column_mappings c LEFT JOIN core.entity_types t ON t.id = c.entity_type_id
                        WHERE c.guid = CAST(:g AS uuid)""", g=str(g)) if g else None
    if not mp:
        raise EditError("No such mapping.", 404)
    return {sheet: {"entity_type": mp["code"], "columns": _j(mp["columns"])}}
