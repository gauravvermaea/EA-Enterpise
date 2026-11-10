"""The organisation part of a whole application backup (owner, 10 Nov 2026, D410): what belongs to the organisation and to no
model or project, so that an application backup carries everything (the infrastructure backup carries it too, as databases).

    organisation/organisation.json   the organisation's own views (not the built-in ones), its own project templates (not the
                                     built-in ones), people's skills, the architecture board's members and the organisation
                                     reference library's folders, entries and versions (rows)
    organisation/library.json        the enterprise library (folders, pages, links and files), from the library service
    organisation/reference/<entry guid>/<file>   each reference library entry's file, from Documents

Restoring puts back, over what is here: the organisation's own views and project templates (by code), skills and board
members (by user name) and the enterprise library. The reference library's rows and files are carried for reading and
for a later restore; they come back with an infrastructure restore (its rows in the database, its files in Documents).
"""

from __future__ import annotations

import json
import zipfile
from typing import Any

from sqlalchemy import text

from . import projects as pj

FORMAT = "eax-organisation/1"
PROJ_TABLES = {   # proj table: (rows kept, the key they are put back by; None: carried only)
    "user_skills": ("SELECT * FROM proj.user_skills ORDER BY username", "username"),
    "board_members": ("SELECT * FROM proj.board_members ORDER BY username", "username"),
    "project_templates": ("SELECT * FROM proj.project_templates WHERE NOT builtin ORDER BY code", "code"),
    "org_ref_folders": ("SELECT * FROM proj.org_ref_folders ORDER BY id", None),
    "org_ref_entries": ("SELECT * FROM proj.org_ref_entries ORDER BY id", None),
    "org_ref_versions": ("SELECT * FROM proj.org_ref_versions ORDER BY id", None),
}
CORE_TABLES = {
    "viewpoints": ("SELECT * FROM core.viewpoints WHERE NOT is_builtin ORDER BY code", "code"),
    # surveys and maturity assessments with their recipients and answers (phases 38.1 and 40); children by the survey's guid
    "surveys": ("SELECT * FROM core.surveys ORDER BY id", "guid"),
    "survey_recipients": ("SELECT * FROM core.survey_recipients ORDER BY id", "guid"),
    "survey_responses": ("SELECT * FROM core.survey_responses ORDER BY id", "guid"),
}


def _cols(conn, schema: str, table: str) -> dict[str, str]:
    """The table's columns and their types (udt names)."""
    return {r[0]: r[1] for r in conn.execute(text("""SELECT column_name, udt_name FROM information_schema.columns
                                                     WHERE table_schema = :s AND table_name = :t ORDER BY ordinal_position"""),
                                             {"s": schema, "t": table})}


def write(z: zipfile.ZipFile, core, pc) -> dict:
    """The organisation part into an open zip; returns what it holds (counts, and what was left out and why)."""
    from . import library_client as lc
    from . import mayan
    data: dict[str, list] = {}
    for t, (sql, _k) in CORE_TABLES.items():
        data[t] = pj._rows(core, sql)
    for t, (sql, _k) in PROJ_TABLES.items():
        try:
            data[t] = pj._rows(pc, sql)
        except Exception:  # noqa: BLE001 - a table an older installation does not have
            data[t] = []
    z.writestr("organisation/organisation.json", json.dumps({"format": FORMAT, "tables": data}, default=str, ensure_ascii=False))
    notes, files = [], 0
    try:
        lib = lc.export_org()
        if lib:
            z.writestr("organisation/library.json", json.dumps(lib, ensure_ascii=False))
    except lc.LibraryDown as exc:
        lib = None
        notes.append(f"the enterprise library was left out: {exc}")
    for e in data.get("org_ref_entries") or []:
        if not e.get("mayan_document_id"):
            continue
        try:
            content, _ct, name = mayan.download(e["mayan_document_id"])
            z.writestr(f"organisation/reference/{e['guid']}/{e.get('file_name') or name or 'file'}", content)
            files += 1
        except Exception as exc:  # noqa: BLE001 - Documents down or the file gone
            notes.append(f"reference file {e.get('file_name')}: {str(exc)[:100]}")
    return {"counts": {t: len(v) for t, v in data.items()} | {"library_entries": len((lib or {}).get("entries") or []),
                                                             "reference_files": files},
            "notes": notes}


def _upsert(conn, schema: str, table: str, key: str, rows: list[dict]) -> int:
    cols = _cols(conn, schema, table)
    n = 0
    for r in rows:
        vals = {c: r[c] for c in cols if c in r and c != "id"}
        for c in vals:
            if cols[c] in ("json", "jsonb") and vals[c] is not None and not isinstance(vals[c], str):
                vals[c] = json.dumps(vals[c])
        names = list(vals)
        placeholders = ", ".join(f"CAST(:{c} AS {cols[c]})" if cols[c] in ("json", "jsonb", "uuid", "timestamptz") else f":{c}"
                                 for c in names)
        sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in names if c not in (key, "guid"))
        conn.execute(text(f"""INSERT INTO {schema}.{table} ({", ".join(names)}) VALUES ({placeholders})
                              ON CONFLICT ({key}) DO UPDATE SET {sets}"""), vals)
        n += 1
    return n


def restore(z: zipfile.ZipFile, core, pc, actor: str) -> tuple[str, list[str]]:
    """Puts the organisation part back (see the module's notes). Returns a sentence and the problems met."""
    from . import library_client as lc
    names = set(z.namelist())
    if "organisation/organisation.json" not in names:
        return "", []
    data = json.loads(z.read("organisation/organisation.json")).get("tables") or {}
    done, problems = [], []
    for schema, tables, conn in (("core", CORE_TABLES, core), ("proj", PROJ_TABLES, pc)):
        for t, (_sql, key) in tables.items():
            if not key or not data.get(t):
                continue
            conn.execute(text("SAVEPOINT org_part"))
            try:
                done.append(f"{_upsert(conn, schema, t, key, data[t])} {t.replace('_', ' ')}")
                conn.execute(text("RELEASE SAVEPOINT org_part"))
            except Exception as exc:  # noqa: BLE001 - one part does not stop the others
                conn.execute(text("ROLLBACK TO SAVEPOINT org_part"))
                problems.append(f"{t}: {str(exc)[:200]}")
    if "organisation/library.json" in names:
        try:
            got = lc.import_org(json.loads(z.read("organisation/library.json")), actor)
            done.append(f"the enterprise library ({got.get('entries', 0)} entries)")
        except lc.LibraryDown as exc:
            problems.append(f"the enterprise library: {exc}")
    if data.get("org_ref_entries"):
        done.append("the reference library is in the file (it comes back with an infrastructure restore)")
    return ("Organisation: " + "; ".join(done) + ".") if done else "", problems


def about(path: Any) -> dict:
    with zipfile.ZipFile(path) as z:
        return {t: len(v) for t, v in (json.loads(z.read("organisation/organisation.json")).get("tables") or {}).items()}
