"""Comparing models and tags (build phase 8.3, D172).

Two sides, each a model as it is now or a tag (a frozen snapshot of any model the person may open), are
compared entity by entity. Entities are matched by hand-made matches first, then by the same guid, by origin
(one was copied from the other, or both from the same entity), by type and display ID, and last by type and
name. Each match is kept (no chosen field differs) or changed (with the fields, a rename counting as one
change); an entity only on the left is eliminated, one only on the right is new. Relationships are matched by
type and their matched ends; the metamodels are compared item by item.

What counts is chosen before comparing (the filter screen): per entity type the fields to compare (name,
description, parent, status, tags, display ID and every attribute), with defaults the tool proposes
(name, description, parent and every attribute; status, tags and display ID left out), the relationship
types, and whether the metamodel counts. System fields (ids, dates, who changed it) never count. The choice
can be saved as a named comparison profile. The result downloads as an Excel workbook.
"""

from __future__ import annotations

import io
import json
from typing import Any

from sqlalchemy.exc import DBAPIError

from . import model_ops as mo
from . import permissions as perms
from . import repository as repo
from . import tags as tg
from .metamodel_edit import EditError, _db_message

BUILT_IN = [("name", "Name", True), ("description", "Description", True), ("parent", "Part of", True),
            ("status", "Status", False), ("tags", "Tags", False), ("display_id", "Display ID", False)]
STATUS_ORDER = ("changed", "new", "eliminated", "kept")


def load_side(conn, side: dict) -> dict:
    """A side of a comparison: {kind: model|tag, id}."""
    if not isinstance(side, dict) or side.get("kind") not in ("model", "tag") or not side.get("id"):
        raise EditError("Each side is a model or a tag: {kind: model|tag, id}.")
    return tg.tag_side(conn, side["id"]) if side["kind"] == "tag" else tg.side_of_model(conn, side["id"])


def _types(spec: dict) -> dict[str, dict]:
    return {t["code"]: t for t in spec.get("entity_types") or []}


def _attr_names(spec: dict) -> dict[str, str]:
    return {a["code"]: a["name"] for a in spec.get("attributes") or []}


def fields_for(left: dict, right: dict) -> dict:
    """The filter screen: every entity type of either side with its fields (and the defaults to compare),
    how many entities each side has, the relationship types, and whether the metamodels differ."""
    lt, rt = _types(left["spec"]), _types(right["spec"])
    names = {**_attr_names(left["spec"]), **_attr_names(right["spec"])}
    count = {"left": {}, "right": {}}
    for k, side in (("left", left), ("right", right)):
        for e in side["snapshot"]["entities"].values():
            count[k][e["type_code"]] = count[k].get(e["type_code"], 0) + 1
    layers = {}
    for spec in (left["spec"], right["spec"]):
        for lay in spec.get("layers") or []:
            layers.setdefault(lay["code"], lay["name"])
    rel_names = {r["code"]: r["name"] for spec in (left["spec"], right["spec"]) for r in spec.get("relationship_types") or []}
    type_names = {c: t["name"] for c, t in {**rt, **lt}.items()}
    # the relationships each type takes part in: allowed by either metamodel, or there in either side's content
    ends: dict[str, dict[tuple[str, str], set[str]]] = {}
    for spec in (left["spec"], right["spec"]):
        for a in spec.get("allowed") or []:
            ends.setdefault(a["source"], {}).setdefault((a["relationship"], "out"), set()).add(a["target"])
            ends.setdefault(a["target"], {}).setdefault((a["relationship"], "in"), set()).add(a["source"])
    for side in (left, right):
        ents = side["snapshot"]["entities"]
        for r in side["snapshot"]["relationships"].values():
            s_t, t_t = (ents.get(r["source"]) or {}).get("type_code"), (ents.get(r["target"]) or {}).get("type_code")
            if s_t and t_t:
                ends.setdefault(s_t, {}).setdefault((r["type_code"], "out"), set()).add(t_t)
                ends.setdefault(t_t, {}).setdefault((r["type_code"], "in"), set()).add(s_t)
    used: dict[str, set[tuple[str, str]]] = {}
    for side in (left, right):
        ents = side["snapshot"]["entities"]
        for r in side["snapshot"]["relationships"].values():
            for g, d in ((r["source"], "out"), (r["target"], "in")):
                if g in ents:
                    used.setdefault(ents[g]["type_code"], set()).add((r["type_code"], d))
    out = []
    for code in sorted(set(lt) | set(rt), key=lambda c: ((lt.get(c) or rt.get(c)).get("layer") or "", (lt.get(c) or rt.get(c))["name"])):
        t = lt.get(code) or rt.get(code)
        # the two sides need not have the same types or attributes: every attribute of either side is offered; one that
        # only one side's type has is marked and left out by default (it would show every entity as changed)
        attrs = []
        on = {k: {i["attribute"] for i in (side_t or {}).get("attributes") or []} for k, side_t in (("left", lt.get(code)), ("right", rt.get(code)))}
        both_have_type = code in lt and code in rt
        for side_t in (lt.get(code), rt.get(code)):
            for i in (side_t or {}).get("attributes") or []:
                if i["attribute"] not in [a["code"] for a in attrs]:
                    only = None
                    if both_have_type and i["attribute"] not in on["left"]:
                        only = "right"
                    elif both_have_type and i["attribute"] not in on["right"]:
                        only = "left"
                    attrs.append({"code": i["attribute"], "label": names.get(i["attribute"], i["attribute"]), "default": only is None,
                                  "section": i.get("section") or "", "only": only})
        fields = [{"code": c, "label": lab, "default": d, "section": "Basic"} for c, lab, d in BUILT_IN] + \
                 [{**a, "code": f"value:{a['code']}"} for a in attrs]
        for (rcode, d), others in sorted((ends.get(code) or {}).items(), key=lambda kv: (rel_names.get(kv[0][0], kv[0][0]), kv[0][1])):
            fields.append({"code": f"rel:{rcode}:{d}", "section": "Relationships", "relationship": rcode, "direction": d,
                           "label": f"{rel_names.get(rcode, rcode)} {'to' if d == 'out' else 'from'}",
                           "others": sorted(type_names.get(o, o) for o in others),
                           "used": (rcode, d) in used.get(code, set()), "default": True})
        out.append({"code": code, "name": t["name"], "layer": layers.get(t.get("layer"), t.get("layer") or ""),
                    "left": count["left"].get(code, 0), "right": count["right"].get(code, 0),
                    "in_left": code in lt, "in_right": code in rt,
                    "default": bool(count["left"].get(code) or count["right"].get(code)), "fields": fields})
    rels = sorted({r["code"]: r["name"] for spec in (left["spec"], right["spec"]) for r in spec.get("relationship_types") or []}.items())
    return {"left": _label(left), "right": _label(right), "types": out,
            "relationship_types": [{"code": c, "name": n, "default": True} for c, n in rels],
            "metamodel_differs": bool(mo.spec_diff(left["spec"], right["spec"]))}


def _label(side: dict) -> dict:
    return {k: side.get(k) for k in ("kind", "model_id", "model", "tag_id", "tag", "commit", "metamodel_version", "label")}


def _rel_fields(fields: list[str]) -> set[tuple[str, str]]:
    return {(f.split(":")[1], f.split(":")[2]) for f in fields if f.startswith("rel:") and f.count(":") == 2}


def defaults(info: dict) -> dict:
    """The tool's proposal: types that have entities, with their default fields; every relationship type."""
    return {"types": {t["code"]: [f["code"] for f in t["fields"] if f["default"]] for t in info["types"] if t["default"]},
            "relationship_types": [r["code"] for r in info["relationship_types"]], "metamodel": True}


# ---------------------------------------------------------------- matching
def match(left: dict, right: dict, manual: dict | None = None) -> dict[str, str]:
    """Left entity guid -> right entity guid."""
    le, re_ = left["snapshot"]["entities"], right["snapshot"]["entities"]
    out: dict[str, str] = {}
    used: set[str] = set()

    def pair(lg, rg):
        if lg in le and rg in re_ and lg not in out and rg not in used:
            out[lg] = rg
            used.add(rg)
    for lg, rg in (manual or {}).items():
        pair(str(lg), str(rg))
    for g in le:
        if g in re_:
            pair(g, g)
    by_origin: dict[str, str] = {}
    for g, e in re_.items():
        by_origin.setdefault(g, g)
        if e.get("origin"):
            by_origin.setdefault(e["origin"], g)
    for g, e in le.items():
        for k in (g, e.get("origin")):
            if k and k in by_origin:
                pair(g, by_origin[k])
                break
    by_id = {(e["type_code"], e["display_id"]): g for g, e in re_.items() if e.get("display_id")}
    for g, e in le.items():
        if e.get("display_id") and (e["type_code"], e["display_id"]) in by_id:
            pair(g, by_id[(e["type_code"], e["display_id"])])
    by_name: dict[tuple, str] = {}
    for g, e in re_.items():
        by_name.setdefault((e["type_code"], e["name"].strip().lower()), g)
    for g, e in le.items():
        k = (e["type_code"], e["name"].strip().lower())
        if k in by_name:
            pair(g, by_name[k])
    return out


def _field(e: dict, f: str, names: dict[str, str]) -> Any:
    if f.startswith("value:"):
        v = e["values"].get(f[6:])
        return names.get(v, v) if v in names else v   # an entity reference shows the entity's name
    if f == "parent":
        return names.get(e.get("parent")) if e.get("parent") else None
    if f == "tags":
        return ", ".join(e.get("tags") or []) or None
    v = e.get(f)
    return v if v not in ("", None) else None


def compare(left: dict, right: dict, settings: dict | None = None) -> dict:
    """Compares two sides with the chosen settings (None: the defaults)."""
    info = fields_for(left, right)
    st = settings or defaults(info)
    want_types: dict[str, list[str]] = st.get("types") or defaults(info)["types"]
    labels = {t["code"]: {f["code"]: f["label"] for f in t["fields"]} for t in info["types"]}
    tinfo = {t["code"]: t for t in info["types"]}
    m = match(left, right, st.get("matches"))
    le, re_ = left["snapshot"]["entities"], right["snapshot"]["entities"]
    rel_names = {r["code"]: r["name"] for spec in (left["spec"], right["spec"]) for r in spec.get("relationship_types") or []}

    def by_entity(side):   # entity guid -> [(relationship type, direction, other end guid, other end name)]
        out: dict[str, list] = {}
        for r in side["snapshot"]["relationships"].values():
            out.setdefault(r["source"], []).append((r["type_code"], "out", r["target"], r["target_name"]))
            out.setdefault(r["target"], []).append((r["type_code"], "in", r["source"], r["source_name"]))
        return out
    lrels, rrels = by_entity(left), by_entity(right)
    lnames = {g: e["name"] for g, e in le.items()}
    rnames = {g: e["name"] for g, e in re_.items()}
    items, summary = [], {}
    matched_right = set(m.values())

    def add(status, code, lft, rgt, changes=None, renamed=False):
        t = tinfo.get(code) or {"name": code, "layer": ""}
        s = summary.setdefault(code, {"entity_type": code, "name": t["name"], "layer": t["layer"], "kept": 0, "changed": 0,
                                       "new": 0, "eliminated": 0})
        s[status] += 1
        items.append({"status": status, "entity_type": code, "entity_type_name": t["name"], "layer": t["layer"],
                      "name": (rgt or lft)["name"], "renamed": renamed, "changes": changes or [],
                      "left": {k: lft[k] for k in ("guid", "name", "display_id")} if lft else None,
                      "right": {k: rgt[k] for k in ("guid", "name", "display_id")} if rgt else None})
    for g, e in le.items():
        code = e["type_code"]
        rg = m.get(g)
        if rg is None:
            if code in want_types:
                add("eliminated", code, e, None)
            continue
        r = re_[rg]
        if code not in want_types and r["type_code"] not in want_types:
            continue
        fields = want_types.get(r["type_code"]) or want_types.get(code) or []
        changes = []
        if r["type_code"] != code:
            changes.append({"field": "type", "label": "Type", "left": e["entity_type"], "right": r["entity_type"]})
        for rcode, d in sorted(_rel_fields(fields)):
            mine = {(m.get(o) or f"left:{o}"): n for t, dd, o, n in lrels.get(g, []) if t == rcode and dd == d}
            theirs = {o: n for t, dd, o, n in rrels.get(rg, []) if t == rcode and dd == d}
            gone = sorted(mine[k] for k in set(mine) - set(theirs))
            added = sorted(theirs[k] for k in set(theirs) - set(mine))
            if gone or added:
                changes.append({"field": f"rel:{rcode}:{d}", "label": f"{rel_names.get(rcode, rcode)} {'to' if d == 'out' else 'from'}",
                                "left": ", ".join(gone) or None, "right": ", ".join(added) or None, "relationship": True})
        for f in fields:
            if f.startswith("rel:"):
                continue
            a, b = _field(e, f, lnames), _field(r, f, rnames)
            if (a or None) != (b or None) and str(a) != str(b):
                changes.append({"field": f, "label": labels.get(r["type_code"], {}).get(f) or labels.get(code, {}).get(f) or f,
                                "left": a, "right": b})
        renamed = any(c["field"] == "name" for c in changes)
        add("changed" if changes else "kept", r["type_code"], e, r, changes, renamed)
    for g, r in re_.items():
        if g not in matched_right and r["type_code"] in want_types:
            add("new", r["type_code"], None, r)
    # relationships, by type and matched ends
    per_type = {code: _rel_fields(f) for code, f in want_types.items()}
    chosen_per_type = any(per_type.values())
    want_rels = set(st.get("relationship_types") or [r["code"] for r in info["relationship_types"]])

    def wanted(r, ents):   # chosen under its source type (outgoing) or its target type (incoming)
        if not chosen_per_type:
            return r["type_code"] in want_rels
        s_t, t_t = (ents.get(r["source"]) or {}).get("type_code"), (ents.get(r["target"]) or {}).get("type_code")
        return (r["type_code"], "out") in per_type.get(s_t, set()) or (r["type_code"], "in") in per_type.get(t_t, set())
    right_rels = {}
    for r in right["snapshot"]["relationships"].values():
        if wanted(r, re_):
            right_rels.setdefault((r["type_code"], r["source"], r["target"]), []).append(r)
    rels = []
    seen = set()
    for r in left["snapshot"]["relationships"].values():
        if not wanted(r, le):
            continue
        k = (r["type_code"], m.get(r["source"]), m.get(r["target"]))
        cand = [x for x in right_rels.get(k, []) if x["guid"] not in seen]
        if cand:
            x = cand[0]
            seen.add(x["guid"])
            status = "changed" if (r.get("name") or "") != (x.get("name") or "") else "kept"
            rels.append({"status": status, "type": r["type_code"], "relationship_type": x["relationship_type"],
                         "source": x["source_name"], "target": x["target_name"],
                         "name_left": r.get("name") or "", "name_right": x.get("name") or ""})
        else:
            rels.append({"status": "eliminated", "type": r["type_code"], "relationship_type": r["relationship_type"],
                         "source": r["source_name"], "target": r["target_name"], "name_left": r.get("name") or "", "name_right": ""})
    for lst in right_rels.values():
        for x in lst:
            if x["guid"] not in seen:
                rels.append({"status": "new", "type": x["type_code"], "relationship_type": x["relationship_type"],
                             "source": x["source_name"], "target": x["target_name"], "name_left": "", "name_right": x.get("name") or ""})
    meta = mo.spec_diff(left["spec"], right["spec"]) if st.get("metamodel", True) else []
    items.sort(key=lambda i: (STATUS_ORDER.index(i["status"]), i["layer"] or "", i["entity_type_name"], i["name"].lower()))
    rels.sort(key=lambda r: (STATUS_ORDER.index(r["status"]), r["relationship_type"], r["source"], r["target"]))
    totals = {s: sum(x[s] for x in summary.values()) for s in ("kept", "changed", "new", "eliminated")}
    rtotals = {s: sum(1 for r in rels if r["status"] == s) for s in ("kept", "changed", "new", "eliminated")}
    return {"left": _label(left), "right": _label(right), "settings": st, "totals": totals, "relationship_totals": rtotals,
            "summary": sorted(summary.values(), key=lambda s: (s["layer"] or "", s["name"])), "items": items, "relationships": rels,
            "metamodel": meta}


# ---------------------------------------------------------------- the result as an Excel workbook
def _entity_rows(e: dict | None, spec: dict, ents: dict) -> dict[str, tuple[str, Any]]:
    """Every field of one entity version, labelled: {key: (label, value)}."""
    if not e:
        return {}
    attrs = _attr_names(spec)
    names = {g: x.get("name") for g, x in ents.items()}
    out = {"name": ("Name", e.get("name")), "entity_type": ("Type", e.get("entity_type")), "display_id": ("Display ID", e.get("display_id")),
           "description": ("Description", e.get("description")), "status": ("Status", e.get("status")),
           "parent": ("Parent", names.get(e.get("parent")) if e.get("parent") else None),
           "tags": ("Tags", ", ".join(e.get("tags") or []))}
    for code, v in (e.get("values") or {}).items():
        out[f"value:{code}"] = (attrs.get(code, code), names.get(v, v) if v in names else v)
    return {k: (lab, v if v not in ("", None) else None) for k, (lab, v) in out.items()}


def _entity_rels(g: str | None, snap: dict) -> dict[tuple, dict]:
    if not g:
        return {}
    out = {}
    for r in (snap.get("relationships") or {}).values():
        if g in (r.get("source"), r.get("target")):
            d = "out" if r.get("source") == g else "in"
            other = r.get("target_name") if d == "out" else r.get("source_name")
            out[(r.get("type_code"), d, (other or "").strip().lower())] = {
                "relationship_type": r.get("relationship_type") or r.get("type_code"), "verb": r.get("verb") or "", "direction": d,
                "other": other}
    return out


def entity_detail(left: dict, right: dict, left_entity: str | None, right_entity: str | None) -> dict:
    """One element side by side (the two versions compared): every field and value of each, and its relationships
    (in both, only in the baseline, only in the target), the differences marked. Relationships are paired by
    type, direction and the name at the other end."""
    le, re_ = left["snapshot"]["entities"], right["snapshot"]["entities"]
    a, b = le.get(left_entity or ""), re_.get(right_entity or "")
    if not a and not b:
        raise EditError("Neither side has this element.", 404)
    ra, rb = _entity_rows(a, left["spec"], le), _entity_rows(b, right["spec"], re_)
    keys = list(ra) + [k for k in rb if k not in ra]
    fixed = ["name", "entity_type", "display_id", "description", "status", "parent", "tags"]
    keys = [k for k in fixed if k in keys] + sorted((k for k in keys if k not in fixed),
                                                    key=lambda k: (ra.get(k) or rb.get(k))[0].lower())
    fields = []
    for k in keys:
        la, va = ra.get(k, (None, None))
        lb, vb = rb.get(k, (None, None))
        if va is None and vb is None:
            continue
        fields.append({"field": k, "label": la or lb, "left": va, "right": vb,
                       "differs": bool(a and b) and str(va or "") != str(vb or ""),
                       "only": None if (k in ra or not a) and (k in rb or not b) else ("left" if k in ra else "right")})
    xa, xb = _entity_rels(left_entity if a else None, left["snapshot"]), _entity_rels(right_entity if b else None, right["snapshot"])
    rels = [{**v, "left": True, "right": k in xb} for k, v in xa.items()] + [{**v, "left": False, "right": True} for k, v in xb.items() if k not in xa]
    rels.sort(key=lambda r: (r["left"] and r["right"], r["direction"], r["relationship_type"] or "", (r["other"] or "").lower()))
    return {"left": {**_label(left), "entity": {"id": left_entity, "name": a.get("name")} if a else None},
            "right": {**_label(right), "entity": {"id": right_entity, "name": b.get("name")} if b else None},
            "status": "changed" if a and b and (any(f["differs"] for f in fields) or any(not (r["left"] and r["right"]) for r in rels))
            else "kept" if a and b else "eliminated" if a else "new",
            "fields": fields, "relationships": rels,
            "differences": sum(1 for f in fields if f["differs"]) + sum(1 for r in rels if not (r["left"] and r["right"]))}


def to_xlsx(result: dict, title: str = "Comparison") -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    bold, head = Font(bold=True), PatternFill("solid", fgColor="DDE6F0")
    fills = {"changed": "FFF4D6", "new": "E3F4E6", "eliminated": "FBE3E1"}

    def sheet(ws, cols, rows, status_col=None):
        ws.append(cols)
        for c in ws[1]:
            c.font, c.fill = bold, head
        for r in rows:
            ws.append(r)
            if status_col is not None and r[status_col] in fills:
                for c in ws[ws.max_row]:
                    c.fill = PatternFill("solid", fgColor=fills[r[status_col]])
        ws.freeze_panes = "A2"
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(60, max(10, *(len(str(c.value or "")) for c in col[:200])))
    ws = wb.active
    ws.title = "Summary"
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["Left (baseline)", result["left"]["label"], f"commit {result['left'].get('commit')}",
               f"metamodel v{result['left'].get('metamodel_version')}"])
    ws.append(["Right (target)", result["right"]["label"], f"commit {result['right'].get('commit')}",
               f"metamodel v{result['right'].get('metamodel_version')}"])
    ws.append([])
    ws.append(["Entities", *[f"{k} {v}" for k, v in result["totals"].items()]])
    ws.append(["Relationships", *[f"{k} {v}" for k, v in result["relationship_totals"].items()]])
    ws.append(["Metamodel differences", len(result["metamodel"])])
    ws.append([])
    start = ws.max_row + 1
    ws.append(["Layer", "Entity type", "Kept", "Changed", "New", "Eliminated"])
    for c in ws[start]:
        c.font, c.fill = bold, head
    for s in result["summary"]:
        ws.append([s["layer"], s["name"], s["kept"], s["changed"], s["new"], s["eliminated"]])
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 22, 40
    sheet(wb.create_sheet("Entities"), ["Status", "Layer", "Entity type", "Name", "Left ID", "Left name", "Right ID", "Right name",
                                        "Fields changed"],
          [[i["status"], i["layer"], i["entity_type_name"], i["name"], (i["left"] or {}).get("display_id"), (i["left"] or {}).get("name"),
            (i["right"] or {}).get("display_id"), (i["right"] or {}).get("name"), ", ".join(c["label"] for c in i["changes"])]
           for i in result["items"]], 0)
    sheet(wb.create_sheet("Field changes"), ["Entity type", "Entity", "Field", "Left (baseline)", "Right (target)"],
          [[i["entity_type_name"], i["name"], c["label"], _cell(c["left"]), _cell(c["right"])]
           for i in result["items"] for c in i["changes"]])
    sheet(wb.create_sheet("Relationships"), ["Status", "Relationship type", "Source", "Target", "Name left", "Name right"],
          [[r["status"], r["relationship_type"], r["source"], r["target"], r["name_left"], r["name_right"]]
           for r in result["relationships"]], 0)
    sheet(wb.create_sheet("Metamodel"), ["Section", "Code", "Name", "Change", "Fields"],
          [[d["section"], d["code"], d["name"], d["change"], "; ".join(f"{f['field']}: {f['old']} -> {f['new']}" for f in d["fields"])]
           for d in result["metamodel"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell(v: Any) -> Any:
    return json.dumps(v) if isinstance(v, (dict, list)) else v


# ---------------------------------------------------------------- comparison profiles
def list_profiles(conn) -> list[dict]:
    """Comparison profiles are shared by everyone (D177)."""
    return [{**p, "id": str(p["id"])} for p in repo._rows(conn, """
        SELECT guid AS id, name, settings, created_by, created_at FROM core.compare_profiles ORDER BY lower(name)""")]


def save_profile(conn, user, name: str, settings: dict) -> dict:
    """Saves (or, under the same name and by its maker, replaces) a profile everyone can use."""
    if not (name or "").strip():
        raise EditError("Give the profile a name.")
    old = repo._rows(conn, "SELECT created_by FROM core.compare_profiles WHERE lower(name) = lower(:n)", n=name.strip())
    if old and old[0]["created_by"] != user.username.lower() and perms.SUPER_ADMIN not in user.roles:
        raise EditError(f"There is already a profile called '{name.strip()}' (made by {old[0]['created_by']}): choose another name.", 409)
    try:
        row = repo._rows(conn, """INSERT INTO core.compare_profiles (name, settings, created_by) VALUES (:n, CAST(:s AS jsonb), :u)
                                  ON CONFLICT (lower(name)) DO UPDATE SET settings = EXCLUDED.settings RETURNING guid""",
                         n=name.strip(), s=json.dumps(settings), u=user.username.lower())[0]
    except DBAPIError as exc:
        raise EditError(_db_message(exc), 409) from exc
    return {"id": str(row["guid"]), "name": name.strip()}


def delete_profile(conn, user, profile: Any) -> dict:
    g = repo._as_guid(profile)
    p = repo._rows(conn, "SELECT guid, name, created_by FROM core.compare_profiles WHERE guid = :g", g=str(g)) if g else []
    if not p:
        raise EditError("No such profile.", 404)
    if p[0]["created_by"] != user.username.lower() and perms.SUPER_ADMIN not in user.roles:
        raise EditError(f"Only {p[0]['created_by']}, who made the profile '{p[0]['name']}', or a Super Admin deletes it.", 403)
    repo._rows(conn, "DELETE FROM core.compare_profiles WHERE guid = :g RETURNING guid", g=str(g))
    return {"deleted": str(g)}
