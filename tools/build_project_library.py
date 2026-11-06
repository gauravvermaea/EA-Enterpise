"""Builds the project library seed (phase 13, D258) from the reviewed master template repository workbook.

    python tools/build_project_library.py [workbook]   (default: docs/requirements/EA_Explorer_Master_Template_Repository.xlsx)

Writes services/api/eax/seed/project_library.json: the phases, the ADM steps, the deliverables and artifacts (one per
group, with every source's row kept), the master folders and the templates. The seed loads it into the proj.lib_*
tables on every start (only what is missing; Super Admins change the library afterwards). Run it again after the
workbook is corrected: rows marked Keep = No are left out, "Merge into Gnnn" moves a row to that group, and the Kind,
Phase, Folder and Rename columns override the suggestions.

The TOGAF template files are never read or copied here (their licence does not allow it): only their names are listed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "services" / "api" / "eax" / "seed" / "project_library.json"


def rows(ws):
    it = ws.iter_rows(values_only=True)
    head = [str(h or "").strip() for h in next(it)]
    for r in it:
        if any(c not in (None, "") for c in r):
            yield {h: ("" if v is None else v) for h, v in zip(head, r, strict=False)}


def keep(v) -> bool:
    return str(v or "").strip().lower() not in ("no", "n", "false")


def main(path: Path) -> dict:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    phases = [dict(code=r["Phase"], name=r["Name"], workspace=r["Workspace folder"], objectives=str(r["Objectives (Meridian framework)"]),
                   inputs=str(r["Inputs (Meridian framework)"]), sort=i)
              for i, r in enumerate(rows(wb["1. Phases"]), 1)]
    steps = [dict(phase=r["Phase"], seq=int(r["#"]), name=r["Step"], source=r["Source"], marking=r["Meridian marking"],
                  note=r["Meridian note"]) for r in rows(wb["2. Steps"]) if keep(r["Keep? (Yes / No)"])]
    groups = {}
    for r in rows(wb["4. Groups"]):
        if not keep(r["Keep? (Yes / No / Merge into Gnnn)"]) and "merge" not in str(r["Keep? (Yes / No / Merge into Gnnn)"]).lower():
            continue
        groups[r["Group"]] = dict(id=r["Group"], phase=r["Phase"], name=str(r["Rename to"] or r["Group name"]),
                                  kind=r["Suggested kind"], type=r["Type"], default=r["Default"], templates=r["Templates"],
                                  sources=[])
    for r in rows(wb["3. Master list"]):
        k = str(r["Keep? (Yes / No / Merge into Gnnn)"] or "")
        gid = r["Group"]
        if k.lower().startswith("merge into"):
            gid = k.split()[-1].strip()
        elif not keep(k):
            continue
        g = groups.get(gid)
        if not g:
            continue
        if not g.get("work"):
            g["work"] = r["Folder"] or r["Working folder (phase workspace)"]
            g["approved"] = r["Approved folder (repository class)"]
            g["kind"] = r["Kind"] or g["kind"]
            g["phase"] = r["Phase"] or g["phase"]
        g["sources"].append(dict(source=r["Source"], phase=r["Source phase"], name=r["Name in source"], kind=r["Kind in source"],
                                 type=r["Type in source"], marking=r["Meridian marking"], note=r["Meridian note"],
                                 files=r["Files / formats"], location=r["Where in source"]))
    folders = [dict(path=r["Folder"], holds=r["Holds"], togaf_class=r["TOGAF repository class"], origin=r["From"])
               for r in rows(wb["5. Folders"]) if keep(r["Keep? (Yes / No)"])]
    templates = [dict(source=r["Source"], code=r["ID"], name=r["Template"], phase=r["Phase"], purpose=r["Purpose"],
                      produced_by=r["Produced by"], approved_by=r["Approved by"], when=r["When"], fields=r["Fields"] or None,
                      folder=r["Folder"]) for r in rows(wb["6. Templates"]) if keep(r["Keep? (Yes / No)"])]
    return dict(version=1, built_from=path.name, phases=phases, steps=steps, items=list(groups.values()), folders=folders,
                templates=templates,
                purposes=[dict(code="strategy", name="Strategy", standard=True), dict(code="portfolio", name="Portfolio", standard=True),
                          dict(code="project", name="Project", standard=True), dict(code="solution", name="Solution", standard=True)])


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "requirements" / "EA_Explorer_Master_Template_Repository.xlsx"
    data = main(src)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"{OUT}: {len(data['phases'])} phases, {len(data['steps'])} steps, {len(data['items'])} items, "
          f"{len(data['folders'])} folders, {len(data['templates'])} templates")
