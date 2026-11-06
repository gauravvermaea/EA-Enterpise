"""Build the EA Explorer template library (phase 13, D264): one starter file per deliverable and artifact of the library.

    python tools/build_ea_explorer_templates.py <Phase-Wise-Deliverables folder> [picks.json]

Where the owner's Meridian sample has the item (the phase-wise deliverables of the fictional Meridian Assurance Group),
that file is used with the Meridian name replaced by "[Organisation]" in every text part (documents, sheets, slides,
properties). Pictures inside the files are kept as they are. Every other item gets a plain starter file written here:
a Word document for deliverables and documents, an Excel workbook for catalogues, matrices and registers, a PowerPoint
deck for diagrams. Nothing is taken from The Open Group's templates.

Writes library/templates/ea-explorer/<item's work folder>/<item name>.<ext> and a manifest (manifest.json, copied to
eax/seed/ea_explorer_templates.json for the seed). The output is committed to git (it is EA Explorer's own).
"""

from __future__ import annotations

import io
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "services" / "api" / "eax" / "seed" / "project_library.json"
OUT = ROOT / "library" / "templates" / "ea-explorer"
ORG = "[Organisation]"

BRAND = [(re.compile(r"Meridian Assurance Group Limited", re.I), ORG), (re.compile(r"Meridian Assurance Group", re.I), ORG),
         (re.compile(r"Meridian Assurance", re.I), ORG), (re.compile(r"(?<![A-Za-z])Meridian(?![a-z])"), ORG), (re.compile(r"(?<![A-Za-z])MERIDIAN(?![A-Z])"), ORG.upper())]
XLSX_KINDS = {"Catalog", "Matrix", "Register", "Record"}
PPTX_KINDS = {"Diagram"}


def safe(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ()&,+-]+", " ", name)).strip()[:90]


def debrand(src: Path) -> bytes:
    """The file with every Meridian name replaced in its text parts (OOXML is a zip of XML parts)."""
    out = io.BytesIO()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.endswith((".xml", ".rels")):
                text = data.decode("utf-8")
                for rx, to in BRAND:
                    text = rx.sub(to, text)
                if info.filename == "[Content_Types].xml" and 'Extension="undefined"' not in text and any(
                        n.endswith(".undefined") for n in zin.namelist()):
                    # some samples hold pictures named *.undefined with no content type: Word repairs them, so declare it
                    text = text.replace("<Default ", '<Default Extension="undefined" ContentType="image/png"/><Default ', 1)
                data = text.encode("utf-8")
            zout.writestr(info, data)
    return out.getvalue()


# ---------------------------------------------------------------- plain starter files
DOC_SECTIONS = ["Document control", "Purpose", "Scope", "Context and drivers", "Content", "Decisions and assumptions",
                "Risks and issues", "Approvals"]


def starter_docx(item: dict, phase: str) -> bytes:
    import docx
    d = docx.Document()
    d.core_properties.title = item["name"]
    d.core_properties.author = ""
    d.add_heading(item["name"], 0)
    d.add_paragraph(f"{ORG} | {phase} | {item['kind']}")
    for sec in DOC_SECTIONS:
        d.add_heading(sec, 1)
        if sec == "Document control":
            t = d.add_table(rows=5, cols=2)
            t.style = "Table Grid"
            for r, k in enumerate(("Version", "Status", "Owner", "Date", "Reviewed by")):
                t.cell(r, 0).text = k
        elif sec == "Approvals":
            t = d.add_table(rows=3, cols=4)
            t.style = "Table Grid"
            for c, k in enumerate(("Name", "Role", "Decision", "Date")):
                t.cell(0, c).text = k
        else:
            d.add_paragraph("[Write this section.]")
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()


def starter_xlsx(item: dict, phase: str) -> bytes:
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Read me"
    for r, (k, v) in enumerate([("Title", item["name"]), ("Organisation", ORG), ("Phase", phase), ("Kind", item["kind"]),
                                ("Version", ""), ("Owner", ""), ("Status", "Draft")], 1):
        ws.cell(r, 1, k).font = Font(bold=True)
        ws.cell(r, 2, v)
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 60
    t = item.get("type") or ""
    data = wb.create_sheet("Matrix" if t == "Matrix" else "Register" if t in ("Register", "Record") else "Catalogue")
    if t == "Matrix":
        heads = ["Row element", "Column element 1", "Column element 2", "Column element 3"]
    elif t in ("Register", "Record"):
        heads = ["ID", "Date", "Title", "Description", "Owner", "Status", "Due", "Notes"]
    else:
        heads = ["ID", "Name", "Description", "Type", "Owner", "Status", "Notes"]
    for c, h in enumerate(heads, 1):
        cell = data.cell(1, c, h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
        data.column_dimensions[cell.column_letter].width = 22
    data.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def starter_pptx(item: dict, phase: str) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    p = Presentation()
    p.slide_width, p.slide_height = Inches(13.333), Inches(7.5)
    s = p.slides.add_slide(p.slide_layouts[0])
    s.shapes.title.text = item["name"]
    s.placeholders[1].text = f"{ORG} | {phase}"
    s = p.slides.add_slide(p.slide_layouts[5])
    s.shapes.title.text = item["name"]
    box = s.shapes.add_textbox(Inches(0.7), Inches(1.6), Inches(12), Inches(0.6))
    box.text_frame.text = "[Draw the diagram here, or paste it from the platform's draw.io.]"
    box.text_frame.paragraphs[0].runs[0].font.size = Pt(16)
    s = p.slides.add_slide(p.slide_layouts[1])
    s.shapes.title.text = "Key points and decisions"
    s.placeholders[1].text = "[Point]"
    out = io.BytesIO()
    p.save(out)
    return out.getvalue()


def ext_for(item: dict) -> str:
    t = item.get("type") or ""
    if t in XLSX_KINDS:
        return "xlsx"
    if t in PPTX_KINDS:
        return "pptx"
    return "docx"


def main(samples: Path, picks_file: Path | None) -> None:
    lib = json.loads(LIB.read_text(encoding="utf-8"))
    phases = {p["code"]: p["name"] for p in lib["phases"]}
    picks = json.loads(picks_file.read_text()) if picks_file else {}
    if OUT.exists():
        for p in OUT.iterdir():
            if p.is_dir():
                shutil.rmtree(p)
    manifest = []
    for item in lib["items"]:
        phase = phases.get(item["phase"], item["phase"])
        src = picks.get(item["id"])
        if src and (samples / src).exists():
            ext = src.rsplit(".", 1)[1].lower()
            data, origin = debrand(samples / src), "Sample, rebranded"
        else:
            ext = ext_for(item)
            data = {"docx": starter_docx, "xlsx": starter_xlsx, "pptx": starter_pptx}[ext](item, phase)
            origin = "Starter"
        rel = f"{item['work']}/{safe(item['name'])}.{ext}"
        (OUT / rel).parent.mkdir(parents=True, exist_ok=True)
        (OUT / rel).write_bytes(data)
        manifest.append({"item": item["id"], "path": rel, "origin": origin})
    text = json.dumps({"library": "EA Explorer", "templates": manifest}, indent=1)
    (OUT / "manifest.json").write_text(text, encoding="utf-8")
    (LIB.parent / "ea_explorer_templates.json").write_text(text, encoding="utf-8")     # what the seed loads
    print(f"{len(manifest)} templates: {sum(m['origin'] != 'Starter' for m in manifest)} from the samples, "
          f"{sum(m['origin'] == 'Starter' for m in manifest)} starters")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
