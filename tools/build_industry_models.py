"""Build the industry reference models (phase 39, D470) from the owner's industry starter packs.

Reads each pack's worked-example repository workbook (`<Industry>_TOGAF_Metamodel.xlsx`, the populated TOGAF content
metamodel of the pack's invented company) and writes `services/api/eax/seed/industry_<code>.py`: entities and
relationships mapped to ArchiMate 4 (D393), in the same shape as `seed/insurance.py`. The workbooks themselves are never
committed; run this on a machine that has them:

    python tools/build_industry_models.py "<folder holding the Industry Specific Guidance packs>"

What is loaded (the industry content and the starter landscape): capabilities with their levels and parents, value
streams, business services, processes, functions, products, business objects (the data entities), the starter
application landscape and its services, technology services, actors and roles, and the relationships between them.
Left out (company-specific or with no ArchiMate 4 home without a new type): drivers, goals, outcomes, measures,
principles, requirements, constraints, assumptions, organisation units, locations, contracts, data components,
technology components, gaps, work packages, projects, governance records, assessments and scores, and the industry
extension types. The word "objective" never appears in what is written (D: use Outcome).
"""

from __future__ import annotations

import pprint
import re
import sys
from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parents[1] / "services" / "api" / "eax" / "seed"

# code, industry name, folder glob under the packs folder, the pack's invented company
PACKS = [
    ("healthcare", "Healthcare", "Health Care/**/Healthcare_TOGAF_Metamodel.xlsx", "Ravensmere Health Network"),
    ("manufacturing", "Manufacturing", "Manufacturing*/**/Manufacturing_TOGAF_Metamodel.xlsx", "Kestrel Industrial Group"),
    ("pharmaceuticals", "Pharmaceuticals", "Pharma/**/Pharmaceuticals_TOGAF_Metamodel.xlsx", "Calderon Therapeutics"),
    ("retail", "Retail", "Retail*/**/Retail_TOGAF_Metamodel.xlsx", "Halverson Stores Group"),
    ("banking", "Banking", "Banking/**/Banking_TOGAF_Metamodel.xlsx", "Ardent Union"),
]
CLASSIFICATIONS = {"Public", "Internal", "Confidential", "Restricted"}


def clean(text) -> str:
    """Plain text, with "objective" always said as outcome."""
    if text is None:
        return ""
    s = str(text).strip()
    s = re.sub(r"\bobjectives\b", "outcomes", s)
    s = re.sub(r"\bObjectives\b", "Outcomes", s)
    s = re.sub(r"\bobjective\b", "outcome", s)
    s = re.sub(r"\bObjective\b", "Outcome", s)
    return s


def rows(wb, prefix: str):
    """The records of the sheet whose name starts with prefix (header on row 4)."""
    name = next(s for s in wb.sheetnames if s.startswith(prefix))
    out = list(wb[name].iter_rows(values_only=True))
    head = [str(h).strip() if h is not None else "" for h in out[3]]
    return [dict(zip(head, r)) for r in out[4:] if r and r[0] not in (None, "")]


def build(path: Path) -> tuple[list, list]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ents, rels = [], []
    names: dict[str, str] = {}      # key -> type
    by_name: dict[tuple[str, str], str] = {}
    seen: set[tuple[str, str, str]] = set()   # one relationship per (source, type, target): the guid is made from them

    def add(key, type_code, name, desc, parent=None, attrs=None):
        key, name = str(key).strip(), clean(name)
        if not name or key in names:
            return
        names[key] = type_code
        by_name[(type_code, name.lower())] = key
        ents.append((key, type_code, name, clean(desc), parent, attrs or {}))

    def link(src, rel, tgt, name=""):
        src, tgt = (str(src).strip() if src else ""), (str(tgt).strip() if tgt else "")
        if src in names and tgt in names and (src, rel, tgt) not in seen and src != tgt:
            seen.add((src, rel, tgt))
            rels.append((src, rel, tgt, name))

    def app_key(v):
        v = str(v or "").strip()
        return v if names.get(v) == "ApplicationComponent" else by_name.get(("ApplicationComponent", v.lower()), v)

    for r in rows(wb, "O13 "):
        level = r.get("Level")
        add(r["Ref"], "Capability", r["Capability"], r.get("Description"), r.get("Parent") or None,
            {"CapabilityLevel": int(level)} if isinstance(level, (int, float)) else {})
    # parents only when the parent is loaded (checked again by the tests)
    ents[:] = [(k, t, n, d, p if (p is None or str(p).strip() in names) else None, a) for k, t, n, d, p, a in ents]
    for r in rows(wb, "O14 "):
        add(r["Ref"], "ValueStream", r["Value stream"], r.get("Scope"))
    for r in rows(wb, "O15 "):
        add(r["Ref"], "Service", r["Business service"], r.get("Description"), attrs={"Domain": "Business"})
    for r in rows(wb, "O16 "):
        add(r["Ref"], "Process", r["Business process"], r.get("Description"))
    for r in rows(wb, "O17 "):
        add(r["Ref"], "Function", r["Business function"], r.get("Description"))
    for r in rows(wb, "O18 "):
        add(r["Ref"], "Product", r["Product"], r.get("Description"))
    for r in rows(wb, "O20 "):
        c = r.get("Classification")
        add(r["Ref"], "BusinessObject", r["Data entity"], r.get("Definition"),
            attrs={"DataClassification": c} if c in CLASSIFICATIONS else {})
    for r in rows(wb, "O23 "):
        add(r["Ref"], "ApplicationComponent", r["Application"], r.get("Description"))
    for r in rows(wb, "O24 "):
        add(r["Ref"], "Service", r["Information system service"], r.get("Description"), attrs={"Domain": "Application"})
    for r in rows(wb, "O25 "):
        add(r["Ref"], "Service", r["Technology service"], r.get("Description"), attrs={"Domain": "Technology"})
    for r in rows(wb, "O10 "):
        add(r["Ref"], "BusinessActor", r["Actor"], f"{clean(r.get('Type'))} actor." if r.get("Type") else "")
    for r in rows(wb, "O11 "):
        add(r["Ref"], "Role", r["Role"], f"{clean(r.get('Type'))} role." if r.get("Type") else "")

    # relationships, ArchiMate 4 (D393); Association where ArchiMate 4 only allows the strict chain
    for r in rows(wb, "O15 "):
        link(r["Ref"], "Realization", r.get("Capability"))                  # business service realises capability
    for r in rows(wb, "O16 "):
        link(r["Ref"], "Realization", r.get("Value stream"))                # process realises value stream
    for r in rows(wb, "O17 "):
        link(r["Ref"], "Realization", r.get("Capability"))                  # function realises capability
    for r in rows(wb, "O24 "):
        link(app_key(r.get("Application")), "Association", r["Ref"], "exposes")
    for r in rows(wb, "R02 "):
        link(r.get("Capability"), "Serving", r.get("Value stream"))         # capability serves value stream
    for r in rows(wb, "R03 "):
        link(r.get("Business service"), "Realization", r.get("Capability"))
    for r in rows(wb, "R04 "):
        link(app_key(r.get("Application")), "Association", r.get("Business service"), "supports")
    for r in rows(wb, "R05 "):
        role = clean(r.get("Role")).lower()
        link(app_key(r.get("Application")), "Access", r.get("Data entity"), f"{role} of the data" if role else "")
    for r in rows(wb, "R06 "):
        link(app_key(r.get("Source")), "Flow", app_key(r.get("Target")), clean(r.get("Type")) or "interface")
    for r in rows(wb, "R21 "):
        link(r.get("Actor"), "Assignment", r.get("Role"))
    for r in rows(wb, "R25 "):
        link(app_key(r.get("Application")), "Association", r.get("Product"), "supports")
    return ents, rels


def write(code: str, industry: str, company: str, src: Path, ents: list, rels: list) -> Path:
    out = OUT / f"industry_{code}.py"
    doc = (f'"""{industry} reference model (phase 39, D470): industry content from the owner\'s {industry} starter pack.\n\n'
           f"Taken from the pack's worked example ({company}, an invented company) and mapped to ArchiMate 4: capabilities\n"
           "with their levels, value streams, business services, processes, functions, products, business objects, the\n"
           "starter application landscape and its services, technology services, actors and roles, and the relationships\n"
           "between them. Keys are the pack's own IDs, stable across releases: the guids are made from them.\n"
           f"Generated by tools/build_industry_models.py from {src.name}; do not edit by hand.\n"
           '"""\n\n')
    body = ("# (key, ArchiMate 4 type code, name, description, parent key, {attribute code: value})\n"
            f"ENTITIES = {pprint.pformat(ents, width=120, sort_dicts=False)}\n\n"
            "# (source key, relationship type, target key, name)\n"
            f"RELATIONSHIPS = {pprint.pformat(rels, width=120)}\n")
    out.write_text(doc + body, encoding="utf-8")
    return out


def main(folder: str) -> int:
    root = Path(folder)
    for code, industry, pattern, company in PACKS:
        found = sorted(root.glob(pattern))
        if not found:
            print(f"{industry}: no worked-example workbook found ({pattern}); not built")
            continue
        ents, rels = build(found[0])
        print(f"{industry}: {len(ents)} entities, {len(rels)} relationships -> {write(code, industry, company, found[0], ents, rels).name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
