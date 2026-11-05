"""Import and export sheets (build phase 10.1, D77, D88, D197): generated from the metamodel.

You choose entity types; the workbook has one sheet per type with every entity and its values, and a Relationships
sheet that comes with them (the relationships between the chosen types). So one download is both an export and the
template to fill in and load back.

    build(conn, model, types, fmt)   -> (bytes, file name, content type)    fmt: xlsx, xlsm or zip (a CSV set)
    read(content, file_name)         -> {"meta": {...}, "sheets": [{"name", "codes", "headers", "rows"}]}

A type's sheet: row 1 the column names (required ones marked *), row 2 the field codes (hidden; how the load knows
each column), rows from 3 the entities. Columns: GUID, ID (display ID), Name, Description, Parent ID, Tags,
then one per attribute, and Delete last. Below the data are empty rows ready to fill: in the .xlsx the ID cell has a formula that gives
a new row a provisional ID (NEW-<prefix>-<n>) as soon as it has a name, so relationships can point to it before it is
loaded; in the .xlsm a macro also writes a real GUID. Pick lists, Yes/No, Parent ID, Delete and every relationship end
are drop-downs. The Relationships sheet: GUID, Source ID, Relationship type, Target ID, Name, the two names looked up,
Delete. A hidden Lists sheet holds the drop-downs' values; a very hidden _eax sheet says which model and types.
A row with no GUID is accepted: it is matched by its ID, or else it is new.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import zipfile
from decimal import Decimal
from typing import Any

from . import repository as repo
from .metamodel_edit import EditError

FORMAT_VERSION = 1
SPARE_MIN, SPARE_MAX = 50, 500           # empty rows added below the data, ready to fill
FIXED = [("guid", "GUID"), ("display_id", "ID"), ("name", "Name"), ("description", "Description"), ("parent", "Parent ID"),
         ("tags", "Tags")]
DELETE = ("delete", "Delete")   # always the last column (owner, 5 Nov 2026), after the attributes
REL_FIXED = [("guid", "GUID"), ("source", "Source ID"), ("relationship_type", "Relationship type"), ("target", "Target ID"),
             ("name", "Name"), ("_source_name", "Source name"), ("_target_name", "Target name"), ("delete", "Delete")]
RELATIONSHIPS = "Relationships"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSM = "application/vnd.ms-excel.sheet.macroEnabled.12"
ZIP = "application/zip"


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, Decimal):
        return format(v.normalize(), "f")
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()[:10] if isinstance(v, dt.date) and not isinstance(v, dt.datetime) else v.isoformat()
    return str(v)


def sheet_name(name: str, taken: set[str]) -> str:
    """An Excel sheet name: at most 31 characters, none of []:*?/\\ and unique."""
    base = re.sub(r"[\[\]:*?/\\]", " ", name).strip()[:31] or "Sheet"
    out, n = base, 2
    while out.lower() in taken:
        suffix = f" ({n})"
        out, n = base[:31 - len(suffix)] + suffix, n + 1
    taken.add(out.lower())
    return out


# ---------------------------------------------------------------- what goes into the sheets
def types_of(conn, model: Any, types: list[str] | None) -> tuple[dict, list[dict]]:
    """The model and the chosen entity types (codes, names or ids; none: every type with entities) with their
    attributes in form order."""
    m = repo.get_model(conn, model)
    all_types = _rows(conn, """SELECT t.id AS _id, t.guid, t.code, t.name, t.id_prefix, l.name AS layer,
                                      (SELECT count(*) FROM core.entities e WHERE e.entity_type_id = t.id AND NOT e.is_deleted) AS n
                                 FROM core.entity_types t JOIN core.layers l ON l.id = t.layer_id
                                WHERE t.model_id = :m AND NOT t.is_deleted ORDER BY l.sort_order, t.sort_order, t.name""", m=m["_id"])
    if types:
        want = {str(x).strip().lower() for x in types if str(x).strip()}
        chosen = [t for t in all_types if {t["code"].lower(), t["name"].lower(), str(t["guid"]).lower()} & want]
        missing = want - {k for t in chosen for k in (t["code"].lower(), t["name"].lower(), str(t["guid"]).lower())}
        if missing:
            raise EditError(f"{m['name']} has no entity type {', '.join(sorted(missing))}.", 404)
    else:
        chosen = [t for t in all_types if t["n"]]
    if not chosen:
        raise EditError("Choose at least one entity type.")
    for t in chosen:
        t["attributes"] = _rows(conn, """
            SELECT at.code, at.name, at.data_type_code AS data_type, ia.is_required, coalesce(ia.help_text, at.description, '') AS help,
                   coalesce((SELECT array_agg(v.value ORDER BY v.sort_order) FROM core.pick_list_values v
                              WHERE v.pick_list_id = at.pick_list_id AND NOT v.is_deleted), ARRAY[]::text[]) AS pick_list_values
              FROM core.item_attributes ia JOIN core.attribute_types at ON at.id = ia.attribute_type_id AND NOT at.is_deleted
             WHERE ia.entity_type_id = :t AND NOT ia.is_deleted ORDER BY ia.sort_order, at.name""", t=t["_id"])
        for a in t["attributes"]:
            a["pick_list_values"] = list(a["pick_list_values"] or [])
    return m, chosen


def content_of(conn, m: dict, chosen: list[dict]) -> tuple[dict[int, list[dict]], list[dict], list[str]]:
    """The entities of the chosen types with their values, the relationships between them, and the relationship
    types the metamodel allows between them (names)."""
    ids = [t["_id"] for t in chosen]
    ents = _rows(conn, """SELECT e.id AS _id, e.entity_type_id AS _type, e.guid, e.display_id, e.name, e.description, e.tags,
                                 p.display_id AS parent
                            FROM core.entities e LEFT JOIN core.entities p ON p.id = e.parent_entity_id
                           WHERE e.model_id = :m AND NOT e.is_deleted AND e.entity_type_id = ANY (CAST(:t AS bigint[]))
                           ORDER BY e.display_id""", m=m["_id"], t=ids)
    vals = _rows(conn, """SELECT v.entity_id AS e, a.code, v.value_text, v.value_number, v.value_date, v.value_bool,
                                 r.display_id AS ref
                            FROM core.attribute_values v JOIN core.attribute_types a ON a.id = v.attribute_type_id
                            JOIN core.entities e ON e.id = v.entity_id
                            LEFT JOIN core.entities r ON r.id = v.value_ref
                           WHERE v.model_id = :m AND NOT v.is_deleted AND v.entity_id IS NOT NULL
                             AND e.entity_type_id = ANY (CAST(:t AS bigint[])) AND NOT e.is_deleted""", m=m["_id"], t=ids)
    by_e: dict[int, dict] = {}
    for v in vals:
        x = next((y for y in (v["value_text"], v["value_number"], v["value_date"], v["value_bool"], v["ref"]) if y is not None), None)
        by_e.setdefault(v["e"], {})[v["code"]] = _text(x)
    out: dict[int, list[dict]] = {}
    for e in ents:
        tags = e["tags"] or []
        if isinstance(tags, str):
            tags = [x for x in tags.strip("{}").replace('"', "").split(",") if x]
        row = {"guid": str(e["guid"]), "display_id": e["display_id"], "name": e["name"], "description": e["description"] or "",
               "parent": e["parent"] or "", "tags": ", ".join(tags), "delete": "", **by_e.get(e["_id"], {})}
        out.setdefault(e["_type"], []).append(row)
    rels = _rows(conn, """SELECT r.guid, s.display_id AS source, rt.name AS relationship_type, t.display_id AS target, r.name
                            FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
                            JOIN core.entities s ON s.id = r.source_entity_id AND NOT s.is_deleted
                            JOIN core.entities t ON t.id = r.target_entity_id AND NOT t.is_deleted
                           WHERE r.model_id = :m AND NOT r.is_deleted
                             AND s.entity_type_id = ANY (CAST(:t AS bigint[])) AND t.entity_type_id = ANY (CAST(:t AS bigint[]))
                           ORDER BY s.display_id, rt.name, t.display_id""", m=m["_id"], t=ids)
    for r in rels:
        r["guid"], r["name"], r["delete"] = str(r["guid"]), r["name"] or "", ""
    allowed = [r["name"] for r in _rows(conn, """SELECT DISTINCT rt.name, rt.sort_order FROM core.allowed_relationships ar
                                                   JOIN core.relationship_types rt ON rt.id = ar.relationship_type_id
                                                  WHERE NOT ar.is_deleted AND ar.source_type_id = ANY (CAST(:t AS bigint[]))
                                                    AND ar.target_type_id = ANY (CAST(:t AS bigint[]))
                                                  ORDER BY rt.sort_order, rt.name""", t=ids)]
    for r in rels:   # a relationship the metamodel does not allow (added from content, D49) still offers its type
        if r["relationship_type"] not in allowed:
            allowed.append(r["relationship_type"])
    return out, rels, allowed


# ---------------------------------------------------------------- building the file
def build(conn, model: Any, types: list[str] | None, fmt: str = "xlsx", actor: str = "") -> tuple[bytes, str, str]:
    m, chosen = types_of(conn, model, types)
    data, rels, allowed = content_of(conn, m, chosen)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    base = re.sub(r"[^\w .-]+", "-", f"{m['name']} sheets {stamp}").strip()
    meta = {"eax": "sheets", "version": FORMAT_VERSION, "model": str(m["id"]), "model_name": m["name"], "made_at": stamp,
            "made_by": actor, "types": [t["code"] for t in chosen]}
    if fmt == "zip":
        return _csv_set(chosen, data, rels, meta), f"{base}.zip", ZIP
    if fmt not in ("xlsx", "xlsm"):
        raise EditError("Choose xlsx, xlsm or zip (a CSV set).")
    content = _workbook(m, chosen, data, rels, allowed, meta, macro=fmt == "xlsm")
    return content, f"{base}.{fmt}", XLSM if fmt == "xlsm" else XLSX


def _columns(t: dict) -> list[tuple[str, str]]:
    return FIXED + [(a["code"], a["name"] + (" *" if a["is_required"] else "")) for a in t["attributes"]] + [DELETE]


def _csv_set(chosen: list[dict], data: dict, rels: list[dict], meta: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        taken: set[str] = set()
        for t in chosen:
            cols = _columns(t)
            s = io.StringIO()
            w = csv.writer(s)
            w.writerow([c for c, _ in cols])     # codes: the header a load reads
            for r in data.get(t["_id"], []):
                w.writerow([r.get(c, "") for c, _ in cols])
            z.writestr(f"{sheet_name(t['code'], taken)}.csv", "﻿" + s.getvalue())
        s = io.StringIO()
        w = csv.writer(s)
        rc = [c for c, _ in REL_FIXED if not c.startswith("_")]
        w.writerow(rc)
        for r in rels:
            w.writerow([r.get(c, "") for c in rc])
        z.writestr("relationships.csv", "﻿" + s.getvalue())
        z.writestr("eax.json", json.dumps(meta, indent=2))
        z.writestr("README.txt", README_CSV)
    return buf.getvalue()


README_CSV = """EA Explorer CSV set (D88): one file per entity type (named by its code) and relationships.csv.
The first line of each file is the field codes. Keep the guid and display_id of rows you change; leave them empty
for new rows (an entity is then new; its relationships can be loaded once it has an ID). delete = Yes deletes the
entity or relationship. Values: dates as YYYY-MM-DD, Yes/No, numbers with a point. UTF-8, comma or semicolon.
"""


def _col(n: int) -> str:
    from openpyxl.utils import get_column_letter
    return get_column_letter(n)


def _workbook(m: dict, chosen: list[dict], data: dict, rels: list[dict], allowed: list[str], meta: dict, macro: bool) -> bytes:
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    head, req, keyf, newf = (PatternFill("solid", fgColor="DDE6F0"), PatternFill("solid", fgColor="FBE3C7"),
                             PatternFill("solid", fgColor="EEEEEE"), PatternFill("solid", fgColor="F3F8EE"))
    bold = Font(bold=True)
    readme = wb.active
    readme.title = "Read me"
    taken = {"read me", "lists", "_eax", RELATIONSHIPS.lower()}
    lists = wb.create_sheet("Lists")
    lists.sheet_state = "hidden"
    lcol = [0]

    def list_column(title: str, values: list[str] | None = None, formulas: list[str] | None = None) -> str:
        """A column of the Lists sheet; its range for a drop-down."""
        lcol[0] += 1
        c = _col(lcol[0])
        lists.cell(1, lcol[0], title).font = bold
        items = formulas if formulas is not None else (values or [])
        for i, v in enumerate(items, start=2):
            lists.cell(i, lcol[0], v)
        return f"Lists!${c}$2:${c}${max(2, len(items) + 1)}"

    sheets = []
    all_id_cells: list[str] = []
    all_name_cells: list[str] = []
    prefixes: set[str] = set()
    for t in chosen:
        name = sheet_name(t["name"], taken)
        rows = data.get(t["_id"], [])
        spare = min(SPARE_MAX, max(SPARE_MIN, len(rows) // 5))
        prefix = re.sub(r"[^A-Z0-9]", "", (t["id_prefix"] or t["code"]).upper())[:8] or "X"
        while prefix in prefixes:
            prefix += "X"
        prefixes.add(prefix)
        last = 2 + len(rows) + spare
        sheets.append({"t": t, "name": name, "rows": rows, "last": last, "prefix": prefix})
        all_id_cells += [f"=IF('{name}'!B{r}=\"\",\"\",'{name}'!B{r})" for r in range(3, last + 1)]
        all_name_cells += [f"=IF('{name}'!C{r}=\"\",\"\",'{name}'!C{r})" for r in range(3, last + 1)]
    ids_range = list_column("Every ID", formulas=all_id_cells)
    names_range = list_column("Every name", formulas=all_name_cells)
    ids_col, names_col = ids_range.split("!")[1].split(":")[0].replace("$2", ""), names_range.split("!")[1].split(":")[0].replace("$2", "")
    yes_range = list_column("Yes", ["Yes"])
    yesno_range = list_column("Yes or No", ["Yes", "No"])

    for s in sheets:
        t, ws = s["t"], wb.create_sheet(s["name"])
        cols = _columns(t)
        attrs = {a["code"]: a for a in t["attributes"]}
        for j, (code, label) in enumerate(cols, start=1):
            c = ws.cell(1, j, label)
            c.font, c.fill = bold, req if label.endswith(" *") or code == "name" else head
            c.alignment = Alignment(wrap_text=True, vertical="top")
            ws.cell(2, j, code)
            a = attrs.get(code)
            tip = {"guid": "The entity's GUID: keep it for rows you change; empty for new rows (the macro version fills it in).",
                   "display_id": "The entity's ID. A new row gets a provisional ID (NEW-...) as soon as it has a name; it becomes "
                                 "the real ID when loaded.",
                   "parent": "The ID of the entity this one is part of (same type).",
                   "tags": "Words to group and find entities by, separated by commas.",
                   "delete": "Yes deletes this entity when the sheet is loaded."}.get(code)
            if a:
                tip = " · ".join(x for x in (a["help"], a["data_type"], "One of: " + ", ".join(a["pick_list_values"])
                                              if a["pick_list_values"] else "") if x)[:900]
            if tip:
                c.comment = Comment(tip, "EA Explorer")
        ws.row_dimensions[2].hidden = True
        for i, r in enumerate(s["rows"], start=3):
            for j, (code, _) in enumerate(cols, start=1):
                v = r.get(code, "")
                if v != "":
                    ws.cell(i, j, v)
        # empty rows ready to fill: a provisional ID as soon as there is a name
        for i in range(3 + len(s["rows"]), s["last"] + 1):
            ws.cell(i, 2, f'=IF(C{i}="","","NEW-{s["prefix"]}-"&TEXT(ROW()-2,"0000"))').fill = newf
        for i in range(3, s["last"] + 1):
            ws.cell(i, 1).fill = keyf
        own = list_column(f"IDs of {s['name']}", formulas=[f"=IF('{s['name']}'!B{r}=\"\",\"\",'{s['name']}'!B{r})"
                                                            for r in range(3, s["last"] + 1)])

        def drop(rng: str, col: int, prompt: str, strict: bool = False, ws=ws, last=s["last"]):
            dv = DataValidation(type="list", formula1=f"={rng}", allow_blank=True, showErrorMessage=strict)
            dv.promptTitle, dv.prompt = "Choose", prompt[:250]
            dv.add(f"{_col(col)}3:{_col(col)}{last}")
            ws.add_data_validation(dv)
        drop(own, 5, "The ID of the entity this one is part of")
        drop(yes_range, len(cols), "Yes deletes it when loaded", strict=True)
        for j, (code, _) in enumerate(cols, start=1):
            a = attrs.get(code)
            if not a:
                continue
            if a["pick_list_values"]:
                drop(list_column(f"{s['name']}: {a['name']}", a["pick_list_values"]), j, f"One of the {a['name']} values")
            elif a["data_type"] == "boolean":
                drop(yesno_range, j, "Yes or No", strict=True)
            elif a["data_type"] == "entity_ref":
                drop(ids_range, j, "The ID of an entity in this workbook (or type an ID or name in the model)")
        widths = {"guid": 12, "display_id": 16, "name": 32, "description": 40, "parent": 14, "tags": 18, "delete": 8}
        for j, (code, label) in enumerate(cols, start=1):
            ws.column_dimensions[_col(j)].width = widths.get(code, max(14, min(40, len(label) + 4)))
        ws.freeze_panes = "D3"
        ws.auto_filter.ref = f"A1:{_col(len(cols))}{max(3, 2 + len(s['rows']))}"

    # relationships between the chosen types: drop-downs of every ID in the workbook and of the allowed types
    ws = wb.create_sheet(RELATIONSHIPS)
    taken.add(RELATIONSHIPS.lower())
    rt_range = list_column("Relationship types", allowed)
    for j, (code, label) in enumerate(REL_FIXED, start=1):
        c = ws.cell(1, j, label)
        c.font, c.fill = bold, head
        ws.cell(2, j, code)
    ws.row_dimensions[2].hidden = True
    spare = min(SPARE_MAX * 2, max(SPARE_MIN * 2, len(rels) // 5))
    last = 2 + len(rels) + spare
    for i, r in enumerate(rels, start=3):
        for j, (code, _) in enumerate(REL_FIXED, start=1):
            if not code.startswith("_") and r.get(code):
                ws.cell(i, j, r[code])
    look = f"Lists!{ids_col}$2:{names_col}${len(all_id_cells) + 1}"
    for i in range(3, last + 1):
        ws.cell(i, 6, f'=IFERROR(VLOOKUP(B{i},{look},2,FALSE),"")')
        ws.cell(i, 7, f'=IFERROR(VLOOKUP(D{i},{look},2,FALSE),"")')
        ws.cell(i, 1).fill = keyf
    for col, rng, prompt, strict in ((2, ids_range, "The source: an ID in this workbook", False),
                                     (3, rt_range, "A relationship type the metamodel allows", True),
                                     (4, ids_range, "The target: an ID in this workbook", False),
                                     (8, yes_range, "Yes removes this relationship when loaded", True)):
        dv = DataValidation(type="list", formula1=f"={rng}", allow_blank=True, showErrorMessage=strict)
        dv.promptTitle, dv.prompt = "Choose", prompt
        dv.add(f"{_col(col)}3:{_col(col)}{last}")
        ws.add_data_validation(dv)
    for j, w in enumerate((12, 16, 24, 16, 24, 32, 32, 8), start=1):
        ws.column_dimensions[_col(j)].width = w
    ws.freeze_panes = "B3"

    _readme(readme, m, chosen, meta, macro)
    hidden = wb.create_sheet("_eax")
    hidden.sheet_state = "veryHidden"
    hidden["A1"] = json.dumps(meta)
    buf = io.BytesIO()
    wb.save(buf)
    out = buf.getvalue()
    if macro:
        from .sheets_vba import add_macro
        out = add_macro(out)
    return out


def _readme(ws, m: dict, chosen: list[dict], meta: dict, macro: bool) -> None:
    from openpyxl.styles import Font
    lines = [
        (f"EA Explorer sheets: {m['name']}", True),
        (f"Made on {meta['made_at']}{' by ' + meta['made_by'] if meta['made_by'] else ''}. Types: "
         + ", ".join(t["name"] for t in chosen) + ".", False),
        ("", False),
        ("How to use it", True),
        ("1. Each type has a sheet with every entity and its values. Change values in place; add new entities in the empty "
         "rows below (green ID cells).", False),
        ("2. Keep the GUID and ID of the rows you change: that is how they are found when loaded. A new row needs no ID: it "
         + ("gets a provisional ID (NEW-...) as soon as it has a name, and the macro writes its GUID."
            if macro else "gets a provisional ID (NEW-...) as soon as it has a name."), False),
        ("3. Relationships: on the Relationships sheet choose the source ID, the relationship type and the target ID from "
         "the drop-downs. New rows' provisional IDs are in the drop-downs too.", False),
        ("4. Delete = Yes deletes an entity or removes a relationship when loaded.", False),
        ("5. Columns marked * are required. Pick lists and Yes/No are drop-downs; dates as YYYY-MM-DD.", False),
        ("6. Load it on the model's Import and export tab in EA Explorer: you see a preview first (new, changed, unchanged, deleted, "
         "problems), can correct rows there, and the rows become your uncommitted changes, which you commit (or ask a "
         "committer to) as with any edit.", False),
        ("", False),
        ("Do not rename the sheets or change the hidden second row: it tells EA Explorer what each column is.", False),
    ]
    for i, (text_, b) in enumerate(lines, start=1):
        ws.cell(i, 1, text_).font = Font(bold=b, size=14 if i == 1 else 11)
    ws.column_dimensions["A"].width = 140


# ---------------------------------------------------------------- reading a file back
def read(content: bytes, file_name: str) -> dict:
    """Every sheet of an uploaded workbook or CSV (set) as rows of {code or header: text}. Sheets made here carry the
    field codes (row 2, or the first line of a CSV); others keep their headers, to be mapped (load preview)."""
    name = (file_name or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        return _read_workbook(content)
    if name.endswith(".zip"):
        return _read_zip(content)
    if name.endswith((".csv", ".txt")):
        return {"meta": {}, "sheets": [_read_csv(content, file_name.rsplit(".", 1)[0])]}
    raise EditError("Load an Excel workbook (.xlsx or .xlsm), a CSV file or a CSV set (.zip).")


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if v.time() == dt.time() else v.isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, bool):
        return "Yes" if v else "No"
    return str(v).strip()


CODE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _read_workbook(content: bytes) -> dict:
    from openpyxl import load_workbook
    try:
        values = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        formulas = load_workbook(io.BytesIO(content), data_only=False, read_only=True)
    except Exception as exc:  # noqa: BLE001 - a damaged or password-protected file
        raise EditError(f"This file cannot be read as an Excel workbook ({exc.__class__.__name__}).") from exc
    meta = {}
    if "_eax" in values.sheetnames:
        try:
            meta = json.loads(values["_eax"]["A1"].value or "{}")
        except ValueError:
            meta = {}
    sheets = []
    for ws in values.worksheets:
        if ws.title in ("Read me", "Lists", "_eax"):
            continue
        fws = formulas[ws.title]
        rows = list(ws.iter_rows(values_only=True))
        frows = list(fws.iter_rows(values_only=True))
        if not rows:
            continue
        headers = [_cell(h) for h in rows[0]]
        second = [_cell(h) for h in rows[1]] if len(rows) > 1 else []
        ours = bool(second) and "name" in second or "source" in second
        codes = second if ours else headers
        body = rows[2:] if ours else rows[1:]
        fbody = frows[2:] if ours else frows[1:]
        out = []
        for n, r in enumerate(body):
            row = {}
            for j, code in enumerate(codes):
                if not code or code.startswith("_") or j >= len(r):
                    continue
                v = _cell(r[j])
                if not v and code == "display_id" and j < len(fbody[n]) and isinstance(fbody[n][j], str) \
                        and fbody[n][j].startswith("=") and "NEW-" in fbody[n][j]:
                    v = "=NEW"     # a provisional ID never calculated (the file was not opened in Excel): worked out on load
                row[code] = v
            if any(v for k, v in row.items() if k not in ("display_id",)) or (row.get("display_id") and row["display_id"] != "=NEW"):
                row["_row"] = n + (3 if ours else 2)
                out.append(row)
        prefix = None
        if ours:
            m_ = re.search(r'"NEW-([A-Z0-9]+)-"', " ".join(str(x) for r in frows[2:] for x in r[1:2] if isinstance(x, str)))
            prefix = m_.group(1) if m_ else None
        sheets.append({"name": ws.title, "ours": ours, "codes": [c for c in codes if c], "headers": headers, "rows": out,
                       "new_prefix": prefix})
    return {"meta": meta, "sheets": sheets}


def _decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _read_csv(content: bytes, name: str) -> dict:
    """A CSV in any of the usual dialects: comma, semicolon or tab; quoted fields; UTF-8 with or without BOM (or
    Windows-1252)."""
    text_ = _decode(content)
    sample = text_[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text_), dialect))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise EditError(f"{name}: the file is empty.")
    headers = [h.strip() for h in rows[0]]
    ours = "name" in headers or "source" in headers
    out = []
    for n, r in enumerate(rows[1:], start=2):
        row = {h: (r[j].strip() if j < len(r) else "") for j, h in enumerate(headers) if h}
        row["_row"] = n
        out.append(row)
    return {"name": name, "ours": ours and all(CODE.match(h) for h in headers if h), "codes": headers, "headers": headers,
            "rows": out, "new_prefix": None, "delimiter": getattr(dialect, "delimiter", ",")}


def _read_zip(content: bytes) -> dict:
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise EditError("This .zip cannot be opened.") from exc
    meta = {}
    if "eax.json" in z.namelist():
        try:
            meta = json.loads(z.read("eax.json"))
        except ValueError:
            meta = {}
    sheets = []
    for n in z.namelist():
        if n.lower().endswith(".csv") and not n.startswith("__MACOSX"):
            sheets.append(_read_csv(z.read(n), n.rsplit("/", 1)[-1][:-4]))
    if not sheets:
        raise EditError("The .zip has no CSV files.")
    return {"meta": meta, "sheets": sheets}
