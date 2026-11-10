"""A model from a metamodel workbook (owner, 10 Nov 2026, D419; built with phase 34, D468).

The workbook holds **the metamodel only** (entity types, attributes, allowed relationships and what goes with them),
never data; data is loaded afterwards with the import sheets (phase 10.1) or a delivery (phase 34). It is our own
template, and round trip: any model's metamodel downloads in the same layout, is edited and loaded as a new model.

    template(conn, model=None)                   the workbook: empty (with drop-downs) or a model's metamodel
    read(content)                                -> a metamodel document (eax-metamodel/1, as model_ops.metamodel_spec)
    preview(conn, user, content, base)           what the new model's metamodel would be: added and changed, errors, warnings
    create(conn, user, content, name, base, ...) the new project model

Sheets (row 1 the field codes, one item a row): Model, Domains, Pick lists, Attributes, Types, Type attributes,
Relationship types, Allowed relationships, Rules, plus Read me and a hidden Lists sheet for the drop-downs. The model
package's metamodel sheets (Entity types, Allowed, Type attributes with owner and code) are read too.

Start **blank** (the workbook is the whole metamodel, on Root) or **from an existing model** (ArchiMate 4, TOGAF 10, a
library or project model you may read): the workbook adds to it, items with a code already there are updated, nothing
is taken away (D289). Whoever may create a model today may do this (Model Creators, Library Admins, Super Admins).
"""

from __future__ import annotations

import io
from typing import Any

from sqlalchemy import text

from . import model_ops as mo
from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError

SHEETS = [   # sheet, section, columns (codes), the package's name for the same sheet
    ("Domains", "domains", ["code", "name", "colour", "description"], "Domains"),
    ("Pick lists", "pick_lists", ["code", "name", "description", "values"], "Pick lists"),
    ("Attributes", "attributes", ["code", "name", "data_type", "pick_list", "unit", "description", "quality_weight"], "Attributes"),
    ("Types", "entity_types", ["code", "name", "domain", "id_prefix", "aspect", "description", "notation", "fill_colour"],
     "Entity types"),
    ("Relationship types", "relationship_types", ["code", "name", "verb", "category", "directed", "description"],
     "Relationship types"),
    ("Allowed relationships", "allowed", ["source", "relationship", "target", "source_multiplicity", "target_multiplicity", "note"],
     "Allowed"),
    ("Rules", "rules", ["entity_type", "attribute", "field", "rule_type", "param1", "param2", "severity", "message"], "Rules"),
]
TYPE_ATTRIBUTES = ["type", "attribute", "required", "section", "default", "help", "quality_weight"]
MAX_ROWS = 20000
YES = {"yes", "y", "true", "1", "x"}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

README = [
    "EA Explorer metamodel workbook (D419): the metamodel only, never data.",
    "Row 1 of each sheet holds the field codes; one item a row. Codes start with a letter and hold letters, digits and _.",
    "Model: the new model's name, framework, version and description (you can change them when you upload).",
    "Domains: the domains types belong to (code, name, colour as six hex digits, description).",
    "Pick lists: values one per line in the cell. Attributes: data_type from the drop-down (url is a Link); list needs a pick list.",
    "Types: the entity types (domain from the drop-down). Type attributes: which attributes each type (or relationship type) has.",
    "Relationship types: directed Yes or No. Allowed relationships: source, relationship, target, multiplicities such as 0..1, 1, 1..*, 0..*.",
    "Rules: optional data quality rules (rule_type from the drop-down; severity error or warning).",
    "Upload it with Models > Model from a metamodel workbook: start blank, or add it to an existing model (it adds and "
    "updates, never takes away). You see what it would make before the model is made.",
]


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def may_create(user) -> bool:
    """Whoever may create a model today (D419): Model Creators, Library Admins and Super Admins."""
    return bool(set(user.roles) & {perms.SUPER_ADMIN, perms.MODEL_CREATOR, perms.LIBRARY_ADMIN})


# ---------------------------------------------------------------- the workbook
def template(conn, model: Any = None) -> tuple[bytes, str]:
    """The workbook: empty with its drop-downs, or a model's metamodel in the same layout (round trip)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    spec = mo.metamodel_spec(conn, model) if model else mo.empty_spec()
    m = repo.get_model(conn, model) if model else None
    data_types = [r["code"] for r in _rows(conn, "SELECT code FROM core.data_types ORDER BY sort_order, code")]
    rule_types = [r["code"] for r in _rows(conn, "SELECT code FROM core.rule_types ORDER BY code")]
    wb = Workbook()
    ws = wb.active
    ws.title = "Read me"
    for line in README:
        ws.append([line])
    ws.column_dimensions["A"].width = 130
    ws["A1"].font = Font(bold=True, size=13)
    bold, fill = Font(bold=True), PatternFill("solid", fgColor="DDE6F0")

    def sheet(title, cols, rows):
        s = wb.create_sheet(title)
        s.append(cols)
        for c in s[1]:
            c.font, c.fill = bold, fill
        for r in rows:
            s.append([_cell(r.get(c)) for c in cols])
        s.freeze_panes = "A2"
        for n, c in enumerate(cols, start=1):
            s.column_dimensions[s.cell(1, n).column_letter].width = 40 if c in ("description", "help", "message", "values") else 18
        return s
    mdl = wb.create_sheet("Model")
    mdl.append(["field", "value"])
    for k, v in (("name", spec.get("name") or ""), ("framework", spec.get("framework") or ""), ("version", spec.get("version") or ""),
                 ("description", (m or {}).get("description") or "")):
        mdl.append([k, v])
    for c in mdl[1]:
        c.font, c.fill = bold, fill
    made = {}
    for title, section, cols, _pkg in SHEETS:
        rows = [dict(r, values="\n".join(r.get("values") or [])) if section == "pick_lists" else r for r in spec.get(section) or []]
        made[section] = sheet(title, cols, rows)
    items = [{"type": t["code"], **i} for t in spec["entity_types"] for i in t.get("attributes") or []]
    items += [{"type": r["code"], **i} for r in spec["relationship_types"] for i in r.get("attributes") or []]
    ta = sheet("Type attributes", TYPE_ATTRIBUTES, items)
    lists = wb.create_sheet("Lists")
    for n, (head, vals) in enumerate((("data_type", data_types), ("rule_type", rule_types), ("yes_no", ["Yes", "No"]),
                                      ("severity", ["error", "warning"])), start=1):
        lists.cell(1, n, head)
        for k, v in enumerate(vals, start=2):
            lists.cell(k, n, v)
    lists.sheet_state = "hidden"

    def dd(ws_, col_letter: str, formula: str):
        v = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=False)
        ws_.add_data_validation(v)
        v.add(f"{col_letter}2:{col_letter}{MAX_ROWS}")
    n_dt, n_rt = len(data_types) + 1, len(rule_types) + 1
    dd(made["attributes"], "C", f"Lists!$A$2:$A${n_dt}")
    dd(made["attributes"], "D", f"'Pick lists'!$A$2:$A${MAX_ROWS}")
    dd(made["entity_types"], "C", f"Domains!$A$2:$A${MAX_ROWS}")
    dd(made["relationship_types"], "E", "Lists!$C$2:$C$3")
    dd(made["allowed"], "A", f"Types!$A$2:$A${MAX_ROWS}")
    dd(made["allowed"], "B", f"'Relationship types'!$A$2:$A${MAX_ROWS}")
    dd(made["allowed"], "C", f"Types!$A$2:$A${MAX_ROWS}")
    dd(made["rules"], "A", f"Types!$A$2:$A${MAX_ROWS}")
    dd(made["rules"], "B", f"Attributes!$A$2:$A${MAX_ROWS}")
    dd(made["rules"], "D", f"Lists!$B$2:$B${n_rt}")
    dd(made["rules"], "G", "Lists!$D$2:$D$3")
    dd(ta, "B", f"Attributes!$A$2:$A${MAX_ROWS}")
    dd(ta, "C", "Lists!$C$2:$C$3")
    buf = io.BytesIO()
    wb.save(buf)
    name = f"{(m or {}).get('name') or 'EA Explorer'} metamodel workbook.xlsx".replace("/", "-")
    return buf.getvalue(), name


def _cell(v):
    if v is True:
        return "Yes"
    if v is False:
        return "No"
    return v


def read(content: bytes) -> dict:
    """The workbook as a metamodel document. Our layout, or a model package's metamodel sheets."""
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - a damaged or password-protected file
        raise EditError(f"This file cannot be read as an Excel workbook ({exc.__class__.__name__}).") from exc

    def rows_of(*titles):
        title = next((t for t in titles if t in wb.sheetnames), None)
        if not title:
            return []
        it = wb[title].iter_rows(values_only=True)
        head = [str(h).strip().lower() if h is not None else "" for h in next(it, [])]
        out = []
        for r in it:
            if r is None or all(v in (None, "") for v in r):
                continue
            out.append({h: ("" if v is None else (v.strip() if isinstance(v, str) else v)) for h, v in zip(head, r, strict=False) if h})
            if len(out) > MAX_ROWS:
                raise EditError(f"{title}: at most {MAX_ROWS} rows.")
        return out
    if not any(t in wb.sheetnames for t in ("Types", "Entity types")):
        raise EditError("This is not a metamodel workbook: it has no Types sheet. Download the template to start from.")
    model = {str(r.get("field") or "").lower(): r.get("value") for r in rows_of("Model")}
    spec = mo.empty_spec(str(model.get("name") or ""), str(model.get("framework") or ""), str(model.get("version") or ""))
    spec["description"] = str(model.get("description") or "")
    for title, section, _cols, pkg in SHEETS:
        spec[section] = [{k: (str(v) if not isinstance(v, (int, float)) or k == "code" else v) for k, v in r.items()}
                         for r in rows_of(title, pkg)]
    for pl in spec["pick_lists"]:
        pl["values"] = [v.strip() for v in str(pl.get("values") or "").replace("\r", "").split("\n") if v.strip()]
    for r in spec["relationship_types"]:
        r["directed"] = str(r.get("directed", "yes") or "yes").lower() in YES
    for a in spec["attributes"]:
        a["quality_weight"] = mo._qw(a.get("quality_weight"))
        a["pick_list"] = a.get("pick_list") or None
    for r in spec["rules"]:
        for k in ("entity_type", "attribute", "field"):
            r[k] = r.get(k) or None
    for section in ("entity_types", "relationship_types"):
        for o in spec[section]:
            o["attributes"] = []
            for k in ("notation", "fill_colour"):
                if k in o and o[k] in ("", None):
                    del o[k]
    types = {str(t.get("code", "")).lower(): t for t in spec["entity_types"]}
    rels = {str(r.get("code", "")).lower(): r for r in spec["relationship_types"]}
    for i in rows_of("Type attributes"):
        code = str(i.get("type") or i.get("code") or "").lower()
        owner = (rels.get(code) if i.get("owner") == "relationship_type" else None) or types.get(code) or rels.get(code)
        item = {"attribute": str(i.get("attribute") or ""), "required": str(i.get("required") or "").lower() in YES,
                "section": str(i.get("section") or ""), "default": i.get("default") if i.get("default") not in ("", None) else None,
                "help": str(i.get("help") or ""), "quality_weight": mo._qw(i.get("quality_weight"))}
        if owner is None:
            spec.setdefault("_orphans", []).append(f"Type attributes: {i.get('type') or i.get('code')!r} is not a type or "
                                                   "relationship type in the workbook or the model it is added to")
            spec.setdefault("_pending_items", []).append((code, item))
        else:
            owner["attributes"].append(item)
    return spec


# ---------------------------------------------------------------- adding to a base
def _key(x: dict) -> str:
    return str(x.get("code") or "").strip().lower()


def merge_specs(base: dict, wb: dict) -> tuple[dict, dict]:
    """The base's metamodel with the workbook added (D289: adds and updates, never takes away), and what changed
    {section: {added: [...], changed: [...]}}."""
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in base.items()}
    out["name"] = wb.get("name") or base.get("name") or ""
    out["framework"] = wb.get("framework") or base.get("framework") or ""
    out["version"] = wb.get("version") or base.get("version") or ""
    what: dict[str, dict] = {}
    for section in ("domains", "pick_lists", "attributes", "entity_types", "relationship_types"):
        items = [dict(i) for i in base.get(section) or []]
        by = {_key(i): i for i in items}
        added, changed = [], []
        for w in wb.get(section) or []:
            k = _key(w)
            if not k:
                continue
            cur = by.get(k)
            if cur is None:
                item = dict(w)
                items.append(item)
                by[k] = item
                added.append(w.get("code"))
                continue
            diff = False
            for f, v in w.items():
                if f in ("attributes", "values", "code"):
                    continue
                if v not in ("", None) and str(cur.get(f) if cur.get(f) is not None else "") != str(v):
                    cur[f] = v
                    diff = True
            if section == "pick_lists":
                extra = [v for v in w.get("values") or [] if v not in (cur.get("values") or [])]
                if extra:
                    cur["values"] = list(cur.get("values") or []) + extra
                    diff = True
            if section in ("entity_types", "relationship_types"):
                have = {str(a["attribute"]).lower(): a for a in cur.get("attributes") or []}
                cur["attributes"] = list(cur.get("attributes") or [])
                for a in w.get("attributes") or []:
                    old = have.get(str(a["attribute"]).lower())
                    if old is None:
                        cur["attributes"].append(a)
                        diff = True
                    elif any(old.get(f) != v for f, v in a.items() if v not in ("", None, False) or f == "required"):
                        old.update({f: v for f, v in a.items() if v not in ("", None) or f == "required"})
                        diff = True
            if diff:
                changed.append(w.get("code"))
        out[section] = items
        what[section] = {"added": added, "changed": changed}
    have = {(str(a["source"]).lower(), str(a["relationship"]).lower(), str(a["target"]).lower()): a for a in base.get("allowed") or []}
    allowed = [dict(a) for a in base.get("allowed") or []]
    index = {(str(a["source"]).lower(), str(a["relationship"]).lower(), str(a["target"]).lower()): a for a in allowed}
    added, changed = [], []
    for a in wb.get("allowed") or []:
        k = (str(a.get("source") or "").lower(), str(a.get("relationship") or "").lower(), str(a.get("target") or "").lower())
        if not all(k):
            continue
        if k not in have:
            item = {kk: a.get(kk) for kk in ("source", "relationship", "target", "note", "source_multiplicity", "target_multiplicity")}
            allowed.append(item)
            index[k] = item
            have[k] = item
            added.append(f"{a['source']} {a['relationship']} {a['target']}")
        else:
            cur = index[k]
            d = False
            for f in ("note", "source_multiplicity", "target_multiplicity"):
                if a.get(f) not in ("", None) and str(cur.get(f) or "") != str(a[f]):
                    cur[f] = a[f]
                    d = True
            if d:
                changed.append(f"{a['source']} {a['relationship']} {a['target']}")
    out["allowed"] = allowed
    what["allowed"] = {"added": added, "changed": changed}
    rk = lambda r: (str(r.get("entity_type") or "").lower(), str(r.get("attribute") or "").lower(),  # noqa: E731
                    str(r.get("field") or "").lower(), str(r.get("rule_type") or ""), str(r.get("param1") or ""), str(r.get("param2") or ""))
    rules = [dict(r) for r in base.get("rules") or []]
    seen = {rk(r) for r in rules}
    new_rules = [r for r in wb.get("rules") or [] if r.get("rule_type") and rk(r) not in seen]
    out["rules"] = rules + [dict(r) for r in new_rules]
    what["rules"] = {"added": [f"{r.get('entity_type') or ''} {r.get('attribute') or r.get('field') or ''} {r['rule_type']}".strip()
                               for r in new_rules], "changed": []}
    # attributes given for types the workbook did not define itself but the base has
    owners = {_key(t): t for t in out["entity_types"]} | {_key(r): r for r in out["relationship_types"]}
    still = []
    for code, item in wb.get("_pending_items") or []:
        o = owners.get(code)
        if o is None:
            still.append(code)
            continue
        if not any(str(a["attribute"]).lower() == str(item["attribute"]).lower() for a in o.get("attributes") or []):
            o.setdefault("attributes", []).append(item)
            if o.get("code") not in what["entity_types"]["changed"] + what["entity_types"]["added"]:
                what["entity_types"]["changed"].append(o.get("code"))
    out["_orphans"] = [f"Type attributes: {c!r} is not a type or relationship type in the workbook or the model it is added to"
                       for c in still]
    return out, what


def _base_spec(conn, user, base: Any) -> tuple[dict, dict | None]:
    if base:
        m = repo.get_model(conn, base)
        if perms.SUPER_ADMIN not in user.roles and m["kind"] == "project" and not perms.model_roles(conn, user.username, m["id"]):
            raise EditError(f"You do not have access to {m['name']}: choose a model you may read.", 403)
        return mo.metamodel_spec(conn, base), m
    top = _rows(conn, """SELECT guid FROM core.models WHERE kind_code = 'template' AND source_model_id IS NULL AND NOT is_deleted
                          ORDER BY id LIMIT 1""")
    if not top:
        raise EditError("Root is missing: the installation is not finished.", 409)
    spec = mo.metamodel_spec(conn, str(top[0]["guid"]))
    return spec, None


def preview(conn, user, content: bytes, base: Any = None) -> dict:
    """What the new model's metamodel would be, before anything is made: counts, what the workbook adds and changes,
    and every error (which stops it) and warning."""
    if not may_create(user):
        raise EditError("Creating a model needs the Model Creator or Library Admin role.", 403)
    wb = read(content)
    base_spec, base_model = _base_spec(conn, user, base)
    combined, what = merge_specs(base_spec, wb)
    findings = [f for f in mo.validate_spec(conn, {k: v for k, v in combined.items() if not k.startswith("_")})]
    findings += [{"level": "error", "where": "Type attributes", "message": m_} for m_ in combined.get("_orphans") or []]
    if not wb["entity_types"] and not base_model:
        findings.append({"level": "error", "where": "Types", "message": "A blank model needs at least one type in the workbook."})
    counts = {s: len(combined.get(s) or []) for s in ("domains", "pick_lists", "attributes", "entity_types", "relationship_types",
                                                      "allowed", "rules")}
    workbook = {s: len(wb.get(s) or []) for s in counts}
    return {"name": wb.get("name") or "", "framework": wb.get("framework") or "", "version": wb.get("version") or "",
            "description": wb.get("description") or "",
            "base": {"id": str(base_model["id"]), "name": base_model["name"]} if base_model else None,
            "workbook": workbook, "counts": counts, "added": {s: v["added"] for s, v in what.items()},
            "changed": {s: v["changed"] for s, v in what.items()},
            "errors": [f for f in findings if f["level"] == "error"], "warnings": [f for f in findings if f["level"] != "error"]}


def create(conn, user, content: bytes, name: str, base: Any = None, description: str = "", icon: str | None = None) -> dict:
    """The new project model: from Root (blank) or from the base model's metamodel, with the workbook added in one new
    metamodel version. The person becomes its Model Admin, as for any new model."""
    p = preview(conn, user, content, base)
    if p["errors"]:
        raise EditError("Fix the workbook first: " + "; ".join(f"{e['where']}: {e['message']}" for e in p["errors"][:6]), 409)
    name = (name or p["name"] or "").strip()
    if not name:
        raise EditError("Give the new model a name.")
    wb = read(content)
    base_spec, base_model = _base_spec(conn, user, base)
    combined, _what = merge_specs(base_spec, wb)
    combined = {k: v for k, v in combined.items() if not k.startswith("_")}
    source = str(base_model["id"]) if base_model else str(_rows(conn, """SELECT guid FROM core.models WHERE kind_code = 'template'
                                                                       AND source_model_id IS NULL AND NOT is_deleted ORDER BY id LIMIT 1""")[0]["guid"])
    made = mo.create_model(conn, user.username, {"kind": "project", "source": source, "copy": "metamodel",
                                                 "name": name, "description": description or p["description"] or
                                                 f"Made from the metamodel workbook{' on ' + base_model['name'] if base_model else ''}.",
                                                 "icon": icon})
    m = made["model"]
    mo._label(conn, f"Metamodel workbook added to {name}")
    version = conn.execute(text("SELECT core.publish_metamodel_version(:m, :n)"),
                           {"m": m["_id"], "n": "Metamodel workbook" + (f" added to {base_model['name']}" if base_model else "")}).scalar_one()
    counts = mo.apply_spec(conn, m["_id"], combined, "merge", False)
    conn.execute(text("UPDATE core.models SET metamodel_name = :f WHERE id = :i"),
                 {"f": (p["framework"] or (base_model or {}).get("metamodel_name") or name)[:200], "i": m["_id"]})
    return {"model": repo.get_model(conn, str(m["id"])), "counts": counts, "version": version, "preview": p}

