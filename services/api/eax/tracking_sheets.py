"""Tracking sheets (owner, 8 Nov 2026, phase 13.2, D325): light sheets kept without the rigour of a metamodel, an
application portfolio or a list of vendors for example. A sheet belongs to a project (anyone who contributes creates,
edits and deletes it) or to the organisation (Super Admins and Library Admins; everyone reads). There are no schema
rules: the columns are whatever was uploaded or added, and every value is text. A sheet is uploaded from Excel (the
first tab) or CSV and downloaded as Excel; uploading again replaces the rows, adds them, or updates the rows matched on
a key column (new rows added, new columns added). Edited in place; only the latest version is kept (the change log
records who changed it). Sheets never count in data quality. (Not eax/sheets.py: that is the metamodel's import and
export sheets, phase 10.1.)
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError

_rows, _one = pj._rows, pj._one
MAX_ROWS = 20000
MAX_COLS = 200
MAX_CELL = 4000


def _scope(conn, scope: str):
    return None if scope == "org" else pj.project_row(conn, scope)


def _may_read(conn, p, user) -> None:
    if p is not None:
        pj._need(conn, p, user, "read")


def may_write(conn, p, user) -> bool:
    if p is None:
        return pj._super_or_library(user)
    try:
        pj._need(conn, p, user, "contribute")
        return not p.get("frozen")
    except EditError:
        return False


def _need_write(conn, p, user) -> None:
    if p is None:
        if not pj._super_or_library(user):
            raise EditError("Organisation sheets are kept by Super Admins and Library Admins.", 403)
    else:
        pj._need(conn, p, user, "contribute")


def _sheet(conn, p, sid: str) -> dict:
    s = _one(conn, f"""SELECT * FROM proj.sheets WHERE guid = CAST(:g AS uuid) AND {'project_id IS NULL' if p is None else 'project_id = :p'}""",
             g=sid, p=p["id"] if p else None)
    if not s:
        raise EditError("No such sheet here.", 404)
    s["columns"] = list(s["columns"] or [])
    return s


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        v = v.isoformat()[:10] if getattr(v, "hour", 0) == 0 and getattr(v, "minute", 0) == 0 else v.isoformat(sep=" ")[:16]
    elif isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()[:MAX_CELL]


def _cols(names: list) -> list[str]:
    """Column names as given, made unique and never empty."""
    out: list[str] = []
    for i, n in enumerate(names):
        n = " ".join(str(n if n is not None else "").split())[:100] or f"Column {i + 1}"
        base, k = n, 2
        while n in out:
            n, k = f"{base} ({k})", k + 1
        out.append(n)
    return out[:MAX_COLS]


def _cells(v: Any) -> dict:
    return v if isinstance(v, dict) else json.loads(v or "{}")


# ---------------------------------------------------------------- reading
def listing(conn, scope: str, user) -> dict:
    p = _scope(conn, scope)
    _may_read(conn, p, user)
    rows = _rows(conn, f"""SELECT s.guid::text AS id, s.name, s.description, s.columns, s.created_by, s.created_at,
                                  coalesce(s.modified_by, s.created_by) AS modified_by, coalesce(s.modified_at, s.created_at) AS modified_at,
                                  (SELECT count(*) FROM proj.sheet_rows r WHERE r.sheet_id = s.id) AS rows
                             FROM proj.sheets s WHERE {'s.project_id IS NULL' if p is None else 's.project_id = :p'} ORDER BY lower(s.name)""",
                 p=p["id"] if p else None)
    for r in rows:
        r["columns"] = list(r["columns"] or [])
        r["rows"] = int(r["rows"])
        for k in ("created_at", "modified_at"):
            r[k] = r[k].isoformat() if hasattr(r[k], "isoformat") else r[k]
    return {"scope": scope, "name": p["name"] if p else "The organisation", "sheets": rows, "may_write": may_write(conn, p, user)}


def get(conn, scope: str, user, sid: str) -> dict:
    p = _scope(conn, scope)
    _may_read(conn, p, user)
    s = _sheet(conn, p, sid)
    rows = [{"id": r["id"], "cells": _cells(r["cells"])} for r in
            _rows(conn, "SELECT id, cells FROM proj.sheet_rows WHERE sheet_id = :s ORDER BY seq, id", s=s["id"])]
    return {"id": sid, "name": s["name"], "description": s["description"], "columns": s["columns"], "rows": rows,
            "modified_by": s.get("modified_by") or s["created_by"], "may_write": may_write(conn, p, user)}


# ---------------------------------------------------------------- writing
def _touch(conn, s: dict, user, columns: list[str] | None = None) -> None:
    conn.execute(text(f"""UPDATE proj.sheets SET modified_by = :u, modified_at = now(){', columns = CAST(:c AS text[])' if columns is not None else ''}
                          WHERE id = :i"""), {"u": user.username, "i": s["id"], "c": columns})


def create(conn, scope: str, user, d: dict) -> dict:
    p = _scope(conn, scope)
    _need_write(conn, p, user)
    name = " ".join((d.get("name") or "").split())[:200]
    if not name:
        raise EditError("Give the sheet a name.")
    cols = _cols([c for c in (d.get("columns") or []) if str(c).strip()]) or ["Name"]
    g = conn.execute(text("""INSERT INTO proj.sheets (project_id, name, description, columns, created_by)
                             VALUES (:p, :n, :d, CAST(:c AS text[]), :u) RETURNING guid::text"""),
                     {"p": p["id"] if p else None, "n": name, "d": (d.get("description") or "").strip()[:2000], "c": cols, "u": user.username}).scalar()
    return {"id": g, "message": f"Sheet {name} made."}


def update(conn, scope: str, user, sid: str, d: dict) -> dict:
    """Its name and description; its columns ({columns}: added, removed, reordered; {renames: {old: new}}); rows
    changed ({rows: [{id, cells}]}), added ({add: [cells]}) and taken out ({delete: [id]})."""
    p = _scope(conn, scope)
    _need_write(conn, p, user)
    s = _sheet(conn, p, sid)
    if "name" in d or "description" in d:
        name = " ".join((d.get("name", s["name"]) or "").split())[:200]
        if not name:
            raise EditError("The name cannot be empty.")
        conn.execute(text("UPDATE proj.sheets SET name = :n, description = :d WHERE id = :i"),
                     {"n": name, "d": (d.get("description", s["description"]) or "").strip()[:2000], "i": s["id"]})
    cols = list(s["columns"])
    renames = {str(k): " ".join(str(v).split())[:100] for k, v in (d.get("renames") or {}).items() if str(v).strip() and str(k) in cols}
    for old, new in renames.items():
        if new in cols and new != old:
            raise EditError(f"There is a column {new} already.")
        conn.execute(text("""UPDATE proj.sheet_rows SET cells = (cells - CAST(:o AS text)) || jsonb_build_object(CAST(:n AS text), cells -> CAST(:o AS text))
                              WHERE sheet_id = :s AND cells ? CAST(:o AS text)"""), {"o": old, "n": new, "s": s["id"]})
        cols = [new if c == old else c for c in cols]
    if "columns" in d:
        new_cols = _cols([c for c in d["columns"] if str(c).strip()])
        if not new_cols:
            raise EditError("A sheet needs a column.")
        for c in cols:
            if c not in new_cols:
                conn.execute(text("UPDATE proj.sheet_rows SET cells = cells - CAST(:c AS text) WHERE sheet_id = :s"), {"c": c, "s": s["id"]})
        cols = new_cols
    for r in d.get("rows") or []:
        cells = {k: _cell(v) for k, v in (r.get("cells") or {}).items() if k in cols}
        conn.execute(text("UPDATE proj.sheet_rows SET cells = cells || CAST(:c AS jsonb) WHERE id = :i AND sheet_id = :s"),
                     {"c": json.dumps(cells), "i": int(r["id"]), "s": s["id"]})
    add = d.get("add") or []
    if add:
        seq = (_one(conn, "SELECT coalesce(max(seq), 0) AS n FROM proj.sheet_rows WHERE sheet_id = :s", s=s["id"]) or {"n": 0})["n"]
        for k, cells in enumerate(add, 1):
            conn.execute(text("INSERT INTO proj.sheet_rows (sheet_id, seq, cells) VALUES (:s, :q, CAST(:c AS jsonb))"),
                         {"s": s["id"], "q": int(seq) + k, "c": json.dumps({c: _cell(v) for c, v in (cells or {}).items() if c in cols})})
    dele = [int(x) for x in d.get("delete") or []]
    if dele:
        conn.execute(text("DELETE FROM proj.sheet_rows WHERE sheet_id = :s AND id = ANY (CAST(:i AS bigint[]))"), {"s": s["id"], "i": dele})
    _touch(conn, s, user, cols if cols != s["columns"] else None)
    return {"message": f"{s['name']} saved."}


def delete(conn, scope: str, user, sid: str) -> dict:
    p = _scope(conn, scope)
    _need_write(conn, p, user)
    s = _sheet(conn, p, sid)
    conn.execute(text("DELETE FROM proj.sheets WHERE id = :i"), {"i": s["id"]})
    return {"message": f"Sheet {s['name']} deleted."}


# ---------------------------------------------------------------- Excel and CSV in and out
def read_file(file_name: str, content: bytes) -> tuple[list[str], list[dict]]:
    """The first tab of a workbook (or a CSV): the first row gives the column names; empty rows are left out."""
    name = (file_name or "").lower()
    if name.endswith(".csv"):
        grid = list(csv.reader(io.StringIO(content.decode("utf-8-sig", errors="replace"))))
    elif name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001 - not a workbook
            raise EditError("That file is not an Excel workbook (.xlsx or .xlsm).") from e
        grid = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    else:
        raise EditError("Upload an Excel workbook (.xlsx, .xlsm) or a CSV file.")
    grid = [r for r in grid if any(_cell(v) for v in r)]
    if not grid:
        raise EditError("The file has no rows.")
    cols = _cols(grid[0])
    if len(grid) - 1 > MAX_ROWS:
        raise EditError(f"{MAX_ROWS} rows at most in a sheet.")
    return cols, [{c: (_cell(r[i]) if i < len(r) else "") for i, c in enumerate(cols)} for r in grid[1:]]


def upload(conn, scope: str, user, sid: str | None, file_name: str, content: bytes, how: str = "replace", key: str = "",
           name: str = "") -> dict:
    """A new sheet from the file (sid empty), or into a sheet: how is replace, add or update (rows matched on key)."""
    p = _scope(conn, scope)
    _need_write(conn, p, user)
    cols, rows = read_file(file_name, content)
    if not sid:
        out = create(conn, scope, user, {"name": name or file_name.rsplit(".", 1)[0], "columns": cols})
        s = _sheet(conn, p, out["id"])
        how = "add"
    else:
        s = _sheet(conn, p, sid)
    if how not in ("replace", "add", "update"):
        raise EditError("Replace the rows, add them, or update them on a key column.")
    allcols = cols if how == "replace" else list(s["columns"]) + [c for c in cols if c not in s["columns"]]
    if len(allcols) > MAX_COLS:
        raise EditError(f"{MAX_COLS} columns at most.")
    added = changed = 0
    if how == "replace":
        conn.execute(text("DELETE FROM proj.sheet_rows WHERE sheet_id = :s"), {"s": s["id"]})
    if how == "update":
        both = [c for c in cols if c in s["columns"]]
        if key not in both:
            raise EditError(f"Pick a key column that is in the sheet and in the file: {', '.join(both) or 'none in both'}.")
        have: dict[str, int] = {}
        for r in _rows(conn, "SELECT id, cells FROM proj.sheet_rows WHERE sheet_id = :s ORDER BY seq", s=s["id"]):
            k = (_cells(r["cells"]).get(key) or "").strip().lower()
            if k:
                have.setdefault(k, r["id"])
        fresh = []
        for r in rows:
            k = (r.get(key) or "").strip().lower()
            if k and k in have:
                conn.execute(text("UPDATE proj.sheet_rows SET cells = cells || CAST(:c AS jsonb) WHERE id = :i"), {"c": json.dumps(r), "i": have[k]})
                changed += 1
            else:
                fresh.append(r)
        rows = fresh
    total = (_one(conn, "SELECT count(*) AS n FROM proj.sheet_rows WHERE sheet_id = :s", s=s["id"]) or {"n": 0})["n"]
    if int(total) + len(rows) > MAX_ROWS:
        raise EditError(f"{MAX_ROWS} rows at most in a sheet.")
    seq = int((_one(conn, "SELECT coalesce(max(seq), 0) AS n FROM proj.sheet_rows WHERE sheet_id = :s", s=s["id"]) or {"n": 0})["n"])
    for k, r in enumerate(rows, 1):
        conn.execute(text("INSERT INTO proj.sheet_rows (sheet_id, seq, cells) VALUES (:s, :q, CAST(:c AS jsonb))"),
                     {"s": s["id"], "q": seq + k, "c": json.dumps(r)})
        added += 1
    _touch(conn, s, user, allcols)
    what = {"replace": f"replaced by {added} rows", "add": f"{added} rows added", "update": f"{changed} rows updated, {added} added"}[how]
    return {"id": str(s["guid"]), "message": f"{s['name']}: {what}."}


def download(conn, scope: str, user, sid: str, only: list[int] | None = None) -> tuple[bytes, str]:
    """The sheet as an Excel workbook (only: the rows shown on the screen after its filters)."""
    import openpyxl
    from openpyxl.styles import Font
    d = get(conn, scope, user, sid)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = (d["name"] or "Sheet")[:31].translate(str.maketrans({c: " " for c in "[]:*?/\\"})) or "Sheet"
    ws.append(d["columns"])
    for c in ws[1]:
        c.font = Font(bold=True)
    keep = set(only) if only else None
    for r in d["rows"]:
        if keep is None or r["id"] in keep:
            ws.append([r["cells"].get(c, "") for c in d["columns"]])
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), f"{d['name']}.xlsx"
