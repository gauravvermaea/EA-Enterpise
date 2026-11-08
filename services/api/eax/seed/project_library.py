"""The project library (phase 13, D258): what an architecture project chooses from in the wizard.

Loaded on every start by the core seed from project_library.json (built from the reviewed master template repository
workbook by tools/build_project_library.py): the purposes, the ADM phases, the steps, the deliverables and artifacts
(each with every source that names it), the master folders, and the template libraries EA Explorer ships (its own,
with a file for every item, and TOGAF 10 by name only, D264). Only what is missing is added, so a Super Admin's changes
to the library are kept. On a laptop with the sample, a sample principles library is added too
(sample_principles.json: the fictional Meridian Assurance Group's architecture and security principles).

The TOGAF template files are not here: only their names. A Super Admin loads the licensed files once (Administration
> Project library); they are stored in Mayan exactly as uploaded.
"""

from __future__ import annotations

import json
from pathlib import Path

from .build import lit

HERE = Path(__file__).resolve().parent


def data() -> dict:
    return json.loads((HERE / "project_library.json").read_text(encoding="utf-8"))


EA_EXPLORER = "EA Explorer"
TOGAF = "TOGAF 10"


def ea_explorer_templates() -> list[dict]:
    """EA Explorer's own templates (built by tools/build_ea_explorer_templates.py; the files are in
    library/templates/ea-explorer, mounted read-only into the API)."""
    f = HERE / "ea_explorer_templates.json"
    return json.loads(f.read_text(encoding="utf-8"))["templates"] if f.exists() else []


def _lib_rows(library: str, cols: list[str], rows: list[list]) -> str:
    """A library's template rows (only the missing ones)."""
    return (f"INSERT INTO proj.lib_templates (library_id, {', '.join(cols)})\n"
            f"SELECT l.id, v.* FROM proj.template_libraries l, (VALUES\n{_values(rows)}\n) AS v ({', '.join(cols)})\n"
            f"WHERE l.name = {lit(library)}\nON CONFLICT (library_id, path) DO NOTHING;\n")


def _values(rows: list[list]) -> str:
    return ",\n".join("(" + ", ".join(lit(v) for v in r) + ")" for r in rows)


def _ins(table: str, cols: list[str], rows: list[list], conflict: str) -> str:
    if not rows:
        return ""
    return f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{_values(rows)}\nON CONFLICT {conflict} DO NOTHING;\n"


CF_ITEMS: dict[str, str] = json.loads((HERE / "content_framework_map.json").read_text(encoding="utf-8"))["document_types"]


def library_sql(d: dict | None = None) -> str:
    d = d or data()
    out = [
        _ins("proj.lib_purposes", ["code", "name", "standard", "sort_order"],
             [[p["code"], p["name"], p["standard"], i * 10] for i, p in enumerate(d["purposes"], 1)], "(code)"),
        _ins("proj.lib_phases", ["code", "name", "workspace", "objectives", "inputs", "sort_order"],
             [[p["code"], p["name"], p["workspace"], p["objectives"], p["inputs"], p["sort"]] for p in d["phases"]], "(code)"),
        _ins("proj.lib_steps", ["phase", "seq", "name", "source", "marking", "note"],
             [[s["phase"], s["seq"], s["name"], s["source"], s["marking"] or "", s["note"] or ""] for s in d["steps"]], "(phase, name)"),
        _ins("proj.lib_items", ["id", "phase", "name", "kind", "type", "default_pick", "work_folder", "approved_folder", "templates",
                                "content_area"],
             [[i["id"], i["phase"], i["name"], i["kind"], i["type"] or "", i["default"] != "Not for use", i["work"], i["approved"] or "",
               i["templates"] or "", CF_ITEMS.get(i["name"], "")] for i in d["items"]], "(id)"),
        # where each document type sits in the content framework (D299): set where it is not chosen yet
        ("UPDATE proj.lib_items i SET content_area = v.a FROM (VALUES\n"
         + _values([[n, a] for n, a in CF_ITEMS.items()]) + "\n) AS v (n, a) WHERE i.name = v.n AND i.content_area = '';\n"),
        _ins("proj.lib_folders", ["path", "holds", "togaf_class", "origin"],
             [[f["path"], f["holds"] or "", f["togaf_class"] or "", f["origin"] or ""] for f in d["folders"]], "(path)"),
        _ins("proj.template_libraries", ["name", "kind", "description", "shared"],
             [[EA_EXPLORER, "ea-explorer", "EA Explorer's own starter templates: a file for every deliverable and artifact, "
               "the worked samples rebranded to [Organisation] where there is one", True],
              [TOGAF, "togaf", "The TOGAF Standard, 10th Edition: Template Deliverables (The Open Group I094). Only their "
               "names ship; a Super Admin loads the licensed files once.", True]], "(name)"),
    ]
    # project templates (D282): the shipped ones, added once; a Super Admin's changes are kept
    tpl = json.loads((HERE / "project_templates.json").read_text(encoding="utf-8"))["templates"]
    out.append(_ins("proj.project_templates", ["code", "name", "icon", "description", "spec", "builtin", "sort_order"],
                    [[t["code"], t["name"], t["icon"], t["description"],
                      json.dumps({k: v for k, v in t.items() if k not in ("code", "name", "icon", "description", "sort")}), True, t["sort"]]
                     for t in tpl], "(code)"))
    # TOGAF's templates by name (files loaded later); the other sources' names are covered by EA Explorer's own files
    togaf = [t for t in d["templates"] if t["source"] == "TOGAF 10"]
    if togaf:
        out.append(_lib_rows(TOGAF, ["path", "source", "code", "name", "phase", "purpose", "folder"],
                             [[f"{t['folder']}/{t['name']}".lstrip("/"), t["source"], t["code"] or "", t["name"], t["phase"] or "",
                               t["purpose"] or "", t["folder"] or ""] for t in togaf]))
    ours = ea_explorer_templates()
    if ours:
        out.append(_lib_rows(EA_EXPLORER, ["path", "item_id", "source", "name", "origin", "file_name"],
                             [[t["path"], t["item"], EA_EXPLORER, t["path"].rsplit("/", 1)[-1], t["origin"], t["path"].rsplit("/", 1)[-1]]
                              for t in ours]))
    # an item's sources: added with the item only (a re-run never duplicates them)
    src = [[i["id"], s["source"], s["phase"] or "", s["name"], s["kind"] or "", s["type"] or "", s["marking"] or "", s["note"] or "",
            s["files"] or "", s["location"] or ""] for i in d["items"] for s in i["sources"]]
    if src:
        out.append("INSERT INTO proj.lib_item_sources (item_id, source, phase, name, kind, type, marking, note, files, location)\n"
                   "SELECT v.* FROM (VALUES\n" + _values(src) + "\n) AS v (item_id, source, phase, name, kind, type, marking, note, files, location)\n"
                   "WHERE NOT EXISTS (SELECT 1 FROM proj.lib_item_sources s WHERE s.item_id = v.item_id);\n")
    return "".join(out)


def sample_principles_sql() -> str:
    d = json.loads((HERE / "sample_principles.json").read_text(encoding="utf-8"))
    return _ins("proj.lib_principles", ["code", "set_name", "category", "name", "statement", "rationale", "implications", "tier", "owner",
                                        "measure", "source"],
                [[p["code"], p["set"], p["category"] or "", p["name"], p["statement"] or "", p["rationale"] or "", p["implications"] or "",
                  p["tier"] or "", p["owner"] or "", p["measure"] or "", "Sample: Meridian Assurance Group (fictional)"]
                 for p in d["principles"]], "(code)")
