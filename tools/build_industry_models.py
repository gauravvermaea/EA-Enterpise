"""Build the industry reference models (phase 39, D470) from the owner's industry starter packs.

Reads each pack's worked-example repository workbook (`<Industry>_TOGAF_Metamodel.xlsx`, the populated TOGAF content
metamodel of the pack's invented company) and writes `services/api/eax/seed/industry_<code>.py`: entities and
relationships mapped to ArchiMate 4 (D393), in the same shape as `seed/insurance.py`. The workbooks themselves are never
committed; run this on a machine that has them:

    python tools/build_industry_models.py [folder]

The folder defaults to library/industry-packs (the packs kept in the repository, owner 10 Nov 2026, D546), one folder per
industry holding `<Industry>_TOGAF_Metamodel.xlsx`. The insurance worked example, Meridian Assurance Group, has a larger
workbook of its own layout (`Insurance/Meridian_TOGAF_Metamodel.xlsx`, "ID"/"Name" columns and its own relationship
sheets): build_meridian() reads it and keeps only relationships ArchiMate 4 allows (an Association where only the strict
chain is allowed, D394), and writes seed/industry_meridian.py (D549).

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
    ("healthcare", "Healthcare", "**/Healthcare_TOGAF_Metamodel.xlsx", "Ravensmere Health Network"),
    ("manufacturing", "Manufacturing", "**/Manufacturing_TOGAF_Metamodel.xlsx", "Kestrel Industrial Group"),
    ("pharmaceuticals", "Pharmaceuticals", "**/Pharmaceuticals_TOGAF_Metamodel.xlsx", "Calderon Therapeutics"),
    ("retail", "Retail", "**/Retail_TOGAF_Metamodel.xlsx", "Halverson Stores Group"),
    ("banking", "Banking", "**/Banking_TOGAF_Metamodel.xlsx", "Ardent Union Bank"),
    ("government", "Government", "**/Government_TOGAF_Metamodel.xlsx", "Northern Province Administration"),
    ("logistics", "Logistics", "**/Logistics_TOGAF_Metamodel.xlsx", "Solway Freight Group"),
    ("minerals_mining", "Minerals and Mining", "**/Minerals_Mining_TOGAF_Metamodel.xlsx", "Drakensberg Resources"),
    ("telecommunications", "Telecommunications", "**/Telecommunications_TOGAF_Metamodel.xlsx", "Northwind Telecom"),
]
MERIDIAN = ("meridian", "Insurance", "**/Meridian_TOGAF_Metamodel.xlsx", "Meridian Assurance Group")
PACKS_DIR = Path(__file__).resolve().parents[1] / "library" / "industry-packs"
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


def _allowed() -> set:
    """ArchiMate 4's allowed relationships (D393), from the seed's own rules."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))
    from eax.seed import build as seed_build
    return {(s, r, t) for s, r, t, _ in seed_build.expand_allowed()}


def build_meridian(path: Path) -> tuple[list, list]:
    """The insurance worked example (Meridian Assurance Group, D549): its own layout ("ID"/"Name", four capability levels,
    relationship sheets named by their ends). Loaded: capabilities (all four levels, with parents), value streams,
    business services, processes, functions, products, data entities, applications, information system and technology
    services, actors and roles; relationships kept only where ArchiMate 4 allows them (else an Association where that is
    allowed, else left out)."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    allowed = _allowed()
    ents, rels, names, seen = [], [], {}, set()

    def add(key, type_code, name, desc, parent=None, attrs=None):
        key, name = str(key or "").strip(), clean(name)
        if not key or not name or key in names:
            return
        names[key] = type_code
        ents.append((key, type_code, name, clean(desc), parent, attrs or {}))

    def link(src, rel, tgt, name=""):
        src, tgt = (str(src).strip() if src else ""), (str(tgt).strip() if tgt else "")
        if src not in names or tgt not in names or src == tgt:
            return
        if (names[src], rel, names[tgt]) not in allowed:
            if (names[src], "Association", names[tgt]) not in allowed:
                return
            rel, name = "Association", name or rel.lower()
        if (src, rel, tgt) not in seen:
            seen.add((src, rel, tgt))
            rels.append((src, rel, tgt, clean(name)))

    def recs(prefix):
        name = next(s for s in wb.sheetnames if s.startswith(prefix))
        out = list(wb[name].iter_rows(values_only=True))
        head = [str(h).strip() if h is not None else "" for h in out[3]]
        return [dict(zip(head, r)) for r in out[4:] if r and r[0] not in (None, "")]

    for r in recs("O13 "):
        level, parent = r.get("Level"), str(r.get("Parent") or "").strip()
        add(r["ID"], "Capability", r["Name"], r.get("Description"), parent if parent and parent != str(r["ID"]).strip() else None,
            {"CapabilityLevel": int(level)} if isinstance(level, (int, float)) else {})
    ents[:] = [(k, t, n, d, p if (p is None or p in names) else None, a) for k, t, n, d, p, a in ents]
    for prefix, type_code, attrs in [("O14 ", "ValueStream", {}), ("O15 ", "Service", {"Domain": "Business"}),
                                     ("O16 ", "Process", {}), ("O17 ", "Function", {}), ("O18 ", "Product", {}),
                                     ("O23 ", "ApplicationComponent", {}), ("O24 ", "Service", {"Domain": "Application"}),
                                     ("O25 ", "Service", {"Domain": "Technology"}), ("O10 ", "BusinessActor", {}),
                                     ("O11 ", "Role", {})]:
        for r in recs(prefix):
            add(r["ID"], type_code, r["Name"], r.get("Description"), attrs=dict(attrs))
    for r in recs("O20 "):
        c = r.get("Classification")
        add(r["ID"], "BusinessObject", r["Name"], r.get("Description"),
            attrs={"DataClassification": c} if c in CLASSIFICATIONS else {})

    def ends(prefix):
        for r in recs(prefix):
            vals = list(r.values())
            yield r, vals[0], vals[2]
    for r in recs("O15 "):
        link(r["ID"], "Realization", r.get("Capability"))                   # business service realises capability
    for r in recs("O16 "):
        link(r["ID"], "Realization", r.get("Value Stream"))                 # process realises value stream
    for r in recs("O24 "):
        link(r.get("Provided By"), "Association", r["ID"], "exposes")       # application exposes its service
        link(r["ID"], "Realization", r.get("Realises Business Service"))
    for _r, s, t in ends("R08 "):
        link(s, "Assignment", t)                                            # actor assigned to role
    for _r, s, t in ends("R11 "):
        link(t, "Serving", s)                                               # capability serves value stream
    for _r, s, t in ends("R12 "):
        link(t, "Realization", s)                                           # business service realises capability
    for _r, s, t in ends("R13 "):
        link(s, "Aggregation", t)                                           # function aggregates process
    for _r, s, t in ends("R14 "):
        link(s, "Realization", t)                                           # process realises business service
    for _r, s, t in ends("R15 "):
        link(t, "Aggregation", s)                                           # product aggregates business service
    for _r, s, t in ends("R20 "):
        link(s, "Association", t, "supports")                               # application supports business service
    for r, s, t in ends("R21 "):
        role = clean(r.get("Role")).lower()
        link(s, "Access", t, f"{role} of the data" if role else "")         # application accesses data entity
    for r, s, t in ends("R23 "):
        link(s, "Flow", t, clean(r.get("Style")) or "interface")            # interface
    for _r, s, t in ends("R24 "):
        link(t, "Serving", s)                                               # technology service serves application
    for _r, s, t in ends("R37 "):
        link(s, "Association", t, "supports")                               # application supports capability (D394)
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
    for code, industry, pattern, company in PACKS + [MERIDIAN]:
        found = sorted(root.glob(pattern))
        if not found:
            print(f"{industry}: no worked-example workbook found ({pattern}); not built")
            continue
        ents, rels = (build_meridian if code == "meridian" else build)(found[0])
        print(f"{industry} ({company}): {len(ents)} entities, {len(rels)} relationships -> "
              f"{write(code, industry, company, found[0], ents, rels).name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else str(PACKS_DIR)))
