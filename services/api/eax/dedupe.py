"""Dedupe within a model (phase 21, D361, D426 to D428).

A wizard:

1. **Find** likely duplicates: entities of one type whose names are the same once case, spaces and punctuation are
   ignored, or close (near spellings; how close is chosen), and, when asked, those with the same values in chosen
   attributes (for example the same vendor and version). Groups that overlap are joined.
2. **Compare** a pair or group side by side: every field with each entity's value; choose the one to keep (the
   survivor) and, field by field, whose value it takes.
3. **Merge**: the survivor takes the chosen values; the others' relationships move to it (one that would repeat a
   relationship it has already is dropped, as are those between the entities merged); the others are removed. Their old
   display IDs and links still find the survivor (core.entity_aliases).

It is the person's own change, made like any other: committed at once when they may commit (one commit, rolled back
from Changes > Commits), else left as their uncommitted changes for a committer. Anyone who may change the model uses
it. Data entry warns when a new name looks like an existing one (similar_names). Rules here, never in the database (D248).
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from sqlalchemy import text

from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError

_rows = repo._rows
MAX_FUZZY = 800          # a type with more entities is matched on exact names only (the near-spelling check is n squared)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def closeness(a: str, b: str) -> float:
    """How alike two names are, 0 to 1, once case, spaces and punctuation are ignored; names whose numbers differ
    (Windows 2016 and 2022, Relational Database 12 and 19) are versions, not duplicates: 0."""
    na, nb = norm(a), norm(b)
    if na == nb:
        return 1.0
    if re.findall(r"\d+", na) != re.findall(r"\d+", nb):
        return 0.0
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    sa, sb = " ".join(sorted(na.split())), " ".join(sorted(nb.split()))
    if sa == sb:                       # the same words in another order: Claims Platform, Platform Claims
        return max(ratio, 0.95)
    return max(ratio, difflib.SequenceMatcher(None, sa, sb).ratio())


def _may_change(conn, user, m: dict) -> None:
    if user is None or perms.SUPER_ADMIN in (user.roles or ()):
        return
    if not set(perms.model_roles(conn, user.username, m["id"])) & perms.MODEL_PERMISSIONS["model.content"]:
        raise EditError(f"Merging duplicates in {m['name']} needs a role that may change it (Architect, Committer, Model Sub Admin "
                        "or Model Admin).", 403)


def _values(conn, model_id: int, codes: list[str]) -> dict[int, dict[str, str]]:
    if not codes:
        return {}
    out: dict[int, dict[str, str]] = {}
    for v in _rows(conn, """SELECT v.entity_id, lower(a.code) AS code,
                                   coalesce(v.value_text, v.value_number::text, v.value_date::text, v.value_bool::text, r.name) AS v
                              FROM core.attribute_values v JOIN core.attribute_types a ON a.id = v.attribute_type_id
                              LEFT JOIN core.entities r ON r.id = v.value_ref
                             WHERE v.model_id = :m AND NOT v.is_deleted AND v.entity_id IS NOT NULL
                               AND lower(a.code) = ANY (CAST(:c AS text[]))""", m=model_id, c=[c.lower() for c in codes]):
        if v["v"] not in (None, ""):
            out.setdefault(v["entity_id"], {})[v["code"]] = str(v["v"])
    return out


class _Groups:
    """Entities joined into groups (union-find), remembering why each pair was joined."""

    def __init__(self, ids: list[str]):
        self.parent = {i: i for i in ids}
        self.why: dict[tuple[str, str], tuple[str, float]] = {}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a: dict, b: dict, reason: str, score: float) -> None:
        ra, rb = self.find(a["id"]), self.find(b["id"])
        if ra != rb:
            self.parent[rb] = ra
        self.why[(a["id"], b["id"])] = (reason, score)


def candidates(conn, model: Any, entity_type: str | None = None, attributes: list[str] | None = None,
               threshold: float = 0.88, by_name: bool = True) -> dict:
    """Groups of likely duplicates: by name (the same, or at least `threshold` alike) and, when attributes are given,
    by the same values in all of them. Each group says why its entities were put together."""
    m = repo.get_model(conn, model)
    threshold = min(max(float(threshold or 0.88), 0.6), 1.0)
    attributes = [a for a in (attributes or []) if a]
    rows = _rows(conn, """SELECT e.id AS _id, e.guid::text AS id, e.name, e.display_id, t.name AS type, t.code
                            FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                           WHERE e.model_id = :m AND NOT e.is_deleted AND NOT t.is_connector
                             AND (CAST(:t AS text) IS NULL OR lower(t.code) = lower(:t) OR lower(t.name) = lower(:t))
                           ORDER BY t.name, e.name""", m=m["_id"], t=entity_type or None)
    vals = _values(conn, m["_id"], attributes)
    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r["code"], []).append(r)
    groups: list[dict] = []
    for _code, ents in by_type.items():
        uf = _Groups([e["id"] for e in ents])
        why = uf.why
        join = uf.join
        find = uf.find
        if by_name:
            if len(ents) > MAX_FUZZY:
                seen: dict[str, dict] = {}
                for e in ents:
                    n = norm(e["name"])
                    if n in seen:
                        join(seen[n], e, "same name", 1.0)
                    else:
                        seen[n] = e
            else:
                for i, a in enumerate(ents):
                    for b in ents[i + 1:]:
                        s = closeness(a["name"], b["name"])
                        if s >= threshold:
                            join(a, b, "same name" if s == 1.0 else "close names", s)
        if attributes:
            seen2: dict[tuple, dict] = {}
            for e in ents:
                v = vals.get(e["_id"], {})
                k = tuple(norm(v.get(a.lower(), "")) for a in attributes)
                if not all(k):
                    continue
                if k in seen2:
                    join(seen2[k], e, "same " + " and ".join(attributes), 1.0)
                else:
                    seen2[k] = e
        bucket: dict[str, list[dict]] = {}
        for e in ents:
            bucket.setdefault(find(e["id"]), []).append(e)
        for g in bucket.values():
            if len(g) < 2:
                continue
            ids = {e["id"] for e in g}
            reasons = sorted({r for (a, b), (r, _s) in why.items() if a in ids and b in ids})
            score = min((s for (a, b), (_r, s) in why.items() if a in ids and b in ids), default=1.0)
            groups.append({"type": g[0]["type"], "type_code": g[0]["code"], "reasons": reasons, "score": round(score * 100),
                           "entities": [{"id": e["id"], "name": e["name"], "display_id": e["display_id"],
                                         "values": {a: vals.get(e["_id"], {}).get(a.lower(), "") for a in attributes}} for e in g]})
    groups.sort(key=lambda g: (g["type"], -g["score"], g["entities"][0]["name"].lower()))
    return {"model": str(m["id"]), "groups": groups[:500], "count": len(groups), "attributes": attributes, "threshold": threshold}


def _state(conn, m: dict, ids: list[str]) -> dict[str, dict]:
    ents = {r["id"]: r for r in _rows(conn, """
        SELECT e.guid::text AS id, e.id AS _id, e.name, e.description, e.display_id, e.entity_type_id AS t, t.name AS type,
               p.guid::text AS parent, p.name AS parent_name, e.created_at, e.created_by, e.modified_at
          FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
          LEFT JOIN core.entities p ON p.id = e.parent_entity_id
         WHERE e.model_id = :m AND NOT e.is_deleted AND e.guid::text = ANY (CAST(:g AS text[]))""", m=m["_id"], g=ids)}
    if len(ents) != len(set(ids)):
        raise EditError("Some of the entities are gone or not in this model.", 404)
    if len({e["t"] for e in ents.values()}) > 1:
        raise EditError("Only entities of the same type are merged.")
    for e in ents.values():
        e["values"], e["shown"] = {}, {}
    by_id = {e["_id"]: e for e in ents.values()}
    for v in _rows(conn, """SELECT v.entity_id, a.code, a.name AS label,
                                   coalesce(v.value_text, v.value_number::text, v.value_date::text, v.value_bool::text, r.guid::text) AS v,
                                   r.name AS ref_name
                              FROM core.attribute_values v JOIN core.attribute_types a ON a.id = v.attribute_type_id
                              LEFT JOIN core.entities r ON r.id = v.value_ref
                             WHERE v.entity_id = ANY (CAST(:e AS bigint[])) AND NOT v.is_deleted AND v.relationship_id IS NULL""",
                   e=list(by_id)):
        if v["v"] in (None, ""):
            continue
        e = by_id[v["entity_id"]]
        e["values"][v["code"]] = v["v"]
        e["shown"][v["code"]] = v["ref_name"] or v["v"]
    for e in ents.values():
        e["relationships"] = _rows(conn, """
            SELECT r.guid::text AS id, rt.code AS type, rt.name AS type_name, s.guid::text AS s, t.guid::text AS t, s.name AS s_name,
                   t.name AS t_name, r.name
              FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
              JOIN core.entities s ON s.id = r.source_entity_id JOIN core.entities t ON t.id = r.target_entity_id
             WHERE r.model_id = :m AND NOT r.is_deleted AND NOT s.is_deleted AND NOT t.is_deleted
               AND (r.source_entity_id = :e OR r.target_entity_id = :e)""", m=m["_id"], e=e["_id"])
    return ents


def _moves(ents: dict[str, dict], keep: str, others: list[str]) -> tuple[list[dict], int]:
    """The others' relationships as they will be on the survivor, and how many are dropped (repeats, or between the
    entities merged)."""
    have = {(r["type"], r["s"], r["t"]) for r in ents[keep]["relationships"]}
    moves, dropped = [], 0
    for o in others:
        for r in ents[o]["relationships"]:
            s = keep if r["s"] in others else r["s"]
            t = keep if r["t"] in others else r["t"]
            k = (r["type"], s, t)
            if s == t or k in have:
                dropped += 1
                continue
            have.add(k)
            moves.append({"type": r["type"], "type_name": r["type_name"], "source": s, "target": t, "name": r["name"] or "",
                          "source_name": ents[keep]["name"] if s == keep else r["s_name"],
                          "target_name": ents[keep]["name"] if t == keep else r["t_name"]})
    return moves, dropped


def compare(conn, model: Any, ids: list[str], keep: str | None = None) -> dict:
    """A pair or group side by side: each field (name, description, part of, every attribute any of them has) with each
    entity's value, which differ, and what merging into `keep` (default: the one with the most relationships and values)
    would move."""
    m = repo.get_model(conn, model)
    ids = list(dict.fromkeys(i for i in ids or [] if i))
    if len(ids) < 2:
        raise EditError("Choose at least two entities to compare.")
    ents = _state(conn, m, ids)
    keep = keep if keep in ents else max(ids, key=lambda i: (len(ents[i]["relationships"]), len(ents[i]["values"]),
                                                             -ids.index(i)))
    labels = {r["code"]: r["name"] for r in _rows(conn, """SELECT a.code, a.name FROM core.item_attributes ia
                                                            JOIN core.attribute_types a ON a.id = ia.attribute_type_id
                                                           WHERE ia.entity_type_id = :t AND NOT ia.is_deleted ORDER BY ia.sort_order, a.name""",
                                                       t=next(iter(ents.values()))["t"])}
    fields = [{"code": "name", "label": "Name", "values": {i: ents[i]["name"] for i in ids}},
              {"code": "description", "label": "Description", "values": {i: ents[i]["description"] or "" for i in ids}},
              {"code": "parent", "label": "Part of", "values": {i: ents[i]["parent_name"] or "" for i in ids}}]
    for code, label in labels.items():
        if any(code in ents[i]["values"] for i in ids):
            fields.append({"code": f"value:{code}", "label": label, "values": {i: ents[i]["shown"].get(code, "") for i in ids}})
    for f in fields:
        vs = {str(v).strip() for v in f["values"].values() if str(v).strip()}
        f["differ"] = len(vs) > 1
        f["empty_in_keep"] = not str(f["values"][keep]).strip()
    others = [i for i in ids if i != keep]
    moves, dropped = _moves(ents, keep, others)
    return {"model": str(m["id"]), "keep": keep, "type": ents[keep]["type"],
            "entities": [{"id": i, "name": ents[i]["name"], "display_id": ents[i]["display_id"], "relationships": len(ents[i]["relationships"]),
                          "values": len(ents[i]["values"]), "created_at": ents[i]["created_at"], "created_by": ents[i]["created_by"],
                          "modified_at": ents[i]["modified_at"]} for i in ids],
            "fields": fields, "moves": moves, "dropped": dropped}


def merge(conn, model: Any, user, keep: str, others: list[str], choices: dict[str, str] | None = None) -> dict:
    """Keeps one entity: it takes the chosen values ({field code: the entity whose value it takes}; a field not chosen
    keeps the survivor's value, or the first other one's when the survivor has none), the others' relationships move to
    it, and they are removed. Committed at once when the person may commit, else left as their changes."""
    from . import commits as cm
    m = repo.get_model(conn, model)
    _may_change(conn, user, m)
    others = [o for o in dict.fromkeys(others or []) if o and o != keep]
    if not others:
        raise EditError("Choose the duplicates to merge into the one kept.")
    ids = [keep] + others
    ents = _state(conn, m, ids)
    k = ents[keep]
    choices = {c: s for c, s in (choices or {}).items() if s in ents}
    data: dict[str, Any] = {}
    values: dict[str, Any] = {}
    for code, src in choices.items():
        if src == keep:
            continue
        e = ents[src]
        if code == "name":
            if e["name"].strip() and e["name"] != k["name"]:
                data["name"] = e["name"]
        elif code == "description":
            if (e["description"] or "") != (k["description"] or ""):
                data["description"] = e["description"] or ""
        elif code == "parent":
            par = e["parent"] or ""
            if par in others:
                par = ""
            if par != (k["parent"] or ""):
                data["parent"] = par
        elif code.startswith("value:"):
            a = code[6:]
            v = e["values"].get(a, "")
            if v != k["values"].get(a, ""):
                values[a] = v
    # fields not chosen: what the survivor lacks is filled from the others, in order (as before, D284)
    if "description" not in choices and not (k["description"] or "").strip():
        d = next(((ents[o]["description"] or "").strip() for o in others if (ents[o]["description"] or "").strip()), "")
        if d:
            data["description"] = d
    for o in others:
        for a, v in ents[o]["values"].items():
            if f"value:{a}" not in choices and a not in k["values"] and a not in values:
                values[a] = v
    if values:
        data["values"] = values
    moves, dropped = _moves(ents, keep, others)
    items: list[tuple[str, dict]] = []
    if data:
        items.append(("entity.update", {"entity": keep, "data": data}))
    items += [("relationship.create", {"data": {"relationship_type": r["type"], "source": r["source"], "target": r["target"],
                                                "name": r["name"], "allow_outside": True}}) for r in moves]
    items += [("entity.delete", {"entity": o}) for o in others]
    res = cm.record_many(conn, m["id"], user.username, items)
    failed = [r["error"] for r in res if not r.get("ok")]
    if failed and any(op == "entity.delete" for (op, _a), r in zip(items, res, strict=True) if not r.get("ok")):
        raise EditError("The merge could not be made: " + "; ".join(failed[:3]), 409)
    for o in others:                                      # the old IDs keep finding the survivor (and earlier merges into them)
        conn.execute(text("""INSERT INTO core.entity_aliases (model_id, old_guid, old_display_id, old_name, survivor_guid, merged_by)
                             VALUES (:m, CAST(:o AS uuid), :d, :n, CAST(:k AS uuid), :u)
                             ON CONFLICT (model_id, old_guid) DO UPDATE SET survivor_guid = EXCLUDED.survivor_guid,
                                    merged_by = EXCLUDED.merged_by, merged_at = now()"""),
                     {"m": m["_id"], "o": o, "d": ents[o]["display_id"] or "", "n": ents[o]["name"], "k": keep, "u": user.username.lower()})
        conn.execute(text("UPDATE core.entity_aliases SET survivor_guid = CAST(:k AS uuid) WHERE model_id = :m AND survivor_guid = CAST(:o AS uuid)"),
                     {"k": keep, "o": o, "m": m["_id"]})
    name = data.get("name") or k["name"]
    done = None
    ids_done = [r["kept"]["change"] for r in res if r.get("ok") and r.get("kept")]
    committed = not cm.uses_commits(m)
    if cm.uses_commits(m) and ids_done and cm.may_commit(conn, user, m):
        done = cm.commit(conn, m["id"], user, None, ids_done, None, f"Duplicates merged into {name}")
        committed = True
    msg = f"{len(others)} merged into {name}"
    if done:
        msg += f" (commit {done['number']}; roll it back from Changes > Commits)"
    elif not committed:
        msg += ": your changes, waiting for a commit (ask a committer, or commit them from Changes)"
    msg += f"; {len(moves)} relationships moved, {dropped} dropped as repeats" + (f"; {len(failed)} changes failed" if failed else "") + "."
    return {"kept": keep, "merged": len(others), "moved": len(moves), "dropped": dropped, "failed": failed[:20],
            "commit": done["number"] if done else None, "committed": committed, "message": msg}


def similar_names(conn, model: Any, entity_type: Any, name: str, exclude: str | None = None, limit: int = 5,
                  all_types: bool = False, threshold: float = 0.85) -> dict:
    """Entities whose names look like this one (data entry and drawn views warn, D361, D454): the same once case, spaces
    and punctuation are ignored, the same words in another order, or close. One matcher (closeness) with dedupe.
    Of the type first; with all_types, other types too, each saying its type and `same_type` false."""
    m = repo.get_model(conn, model)
    name = (name or "").strip()
    limit = min(max(int(limit or 5), 1), 20)
    if len(norm(name)) < 3:
        return {"similar": []}
    et = repo._find_type(conn, m["_id"], entity_type) if entity_type else None
    if et is None and not all_types:
        return {"similar": []}
    rows = _rows(conn, """SELECT e.guid::text AS id, e.name, e.display_id, t.code AS type_code, t.name AS type,
                                 (e.entity_type_id = CAST(:t AS bigint)) AS same_type
                            FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                           WHERE e.model_id = :m AND NOT e.is_deleted AND NOT t.is_connector
                             AND (:alltypes OR e.entity_type_id = CAST(:t AS bigint))
                             AND (CAST(:x AS text) IS NULL OR e.guid::text <> :x) LIMIT 20000""",
                 m=m["_id"], t=et["_id"] if et else None, alltypes=bool(all_types), x=exclude or None)
    hits = []
    for r in rows:
        s = closeness(name, r["name"])
        if s >= threshold:
            hits.append({**r, "same_type": bool(r["same_type"]), "score": round(s * 100), "same": s == 1.0})
    hits.sort(key=lambda h: (not h["same_type"], -h["score"], h["name"]))
    return {"similar": hits[:limit]}


def alias(conn, m: dict, ref: str) -> dict | None:
    """The survivor an old guid or display ID of a merged entity now means, if any: {survivor, old_display_id, old_name}."""
    g = repo._as_guid(ref)
    row = _rows(conn, f"""SELECT survivor_guid::text AS survivor, old_display_id, old_name FROM core.entity_aliases
                           WHERE model_id = :m AND {"old_guid = CAST(:r AS uuid)" if g else "lower(old_display_id) = lower(:r)"}
                           ORDER BY merged_at DESC LIMIT 1""", m=m["_id"], r=str(g or ref))
    return row[0] if row else None


def to_xlsx(result: dict, model_name: str, base: str = "", searched: str = "") -> bytes:
    """The likely duplicates as an Excel workbook (owner, 10 Nov 2026, D541): sheet Duplicates, one row per entity of each
    group (the group's number, type, why they were put together, how alike, the entity with a link back, its display ID,
    the matched attributes' values); sheet About: what was searched and when. Empty groups give a workbook that says so."""
    import io
    from datetime import UTC, datetime

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    head, bold, link = PatternFill("solid", fgColor="E9ECEF"), Font(bold=True), Font(color="1D5FD1", underline="single")
    wb = Workbook()
    ws = wb.active
    ws.title = "Duplicates"
    attrs = list(result.get("attributes") or [])
    header = ["Group", "Entity type", "Why", "How alike (%)", "Entity", "Display ID", *attrs, "Link"]
    ws.append(header)
    for i, w in enumerate([8, 26, 30, 14, 40, 14, *([20] * len(attrs)), 60], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
        ws.cell(1, i).font, ws.cell(1, i).fill = bold, head
    ws.freeze_panes = "A2"
    base = (base or "").rstrip("/")
    for n, g in enumerate(result.get("groups") or [], 1):
        for e in g["entities"]:
            url = f"{base}/#/metamodel/{result.get('model')}/entity/{e['id']}" if base else ""
            ws.append([n, g["type"], ", ".join(g["reasons"]), g["score"], e["name"], e["display_id"],
                       *[(e.get("values") or {}).get(a, "") for a in attrs], url])
            if url:
                c = ws.cell(ws.max_row, len(header))
                c.hyperlink, c.font = url, link
                ws.cell(ws.max_row, 5).hyperlink, ws.cell(ws.max_row, 5).font = url, link
    if not result.get("groups"):
        ws.append(["", "No likely duplicates found."])
    else:
        ws.auto_filter.ref = ws.dimensions
    ab = wb.create_sheet("About")
    ab.column_dimensions["A"].width, ab.column_dimensions["B"].width = 22, 80
    for k, v in [("Model", model_name), ("Searched", searched or "every entity type"),
                 ("Names alike from", f"{round(float(result.get('threshold') or 0) * 100)}%"),
                 ("Matched attributes", ", ".join(attrs) or "none"), ("Groups found", result.get("count", 0)),
                 ("Made", datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"))]:
        ab.append([k, v])
        ab.cell(ab.max_row, 1).font = bold
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
