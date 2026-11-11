"""Builds every test data file, the same bytes every time (D580): `python -m testbench.data build`.

The built files are committed (all small); this program is how they are made again after a change. manifest.json lists
each file with what it is for, who uses it and its checksum; `python -m testbench.data check` says whether the files
on disk are the ones this program makes. Only openpyxl is needed (Word, PDF and PNG files are written directly).

The inside self-test reads the same folder: the test runner container mounts it at /testdata (docker-compose.yml,
EAX_TEST_DATA), and manifest.json's keys are the names both use."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import struct
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXED = (2026, 11, 1, 0, 0, 0)                  # every zip entry's date: the same bytes on every build
TAG = "Self-test data"                          # every name made here starts with it, so it is easy to find and remove

# ------------------------------------------------------------------ the data itself (one place)
APPLICATIONS = [   # name, description, Vendor, Version, Hosting, Url
    (f"{TAG} Quote Optimiser", "Prices quotes for brokers", "Kestrel Labs", "1.4", "SaaS",
     "https://quote.example.org | product page"),
    (f"{TAG} Broker Portal", "Where brokers place business", "", "3.2", "On premises",
     "https://portal.example.org/help | broker help"),
    (f"{TAG} Claims Hub", "Takes and settles claims", "Tidewater Systems", "7.0", "Cloud", ""),
]
NODES = [(f"{TAG} Container Platform", "Runs the containers"), (f"{TAG} Data Warehouse Server", "Holds the reporting data")]
RELATIONSHIPS = [  # source, relationship_type, target, name
    (f"{TAG} Container Platform", "Serving", f"{TAG} Quote Optimiser", "hosts"),
    (f"{TAG} Container Platform", "Serving", f"{TAG} Broker Portal", "hosts"),
    (f"{TAG} Quote Optimiser", "Flow", f"{TAG} Broker Portal", "quotes"),
]
APP_COLS = [("name", "Name *"), ("description", "Description"), ("Vendor", "Vendor"), ("Version", "Version"),
            ("Hosting", "Hosting"), ("Url", "Url")]


def _zip(entries: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name, data in entries:
            info = zipfile.ZipInfo(name, FIXED)
            info.compress_type = zipfile.ZIP_STORED     # stored: the same bytes whatever zlib this Python has
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    return buf.getvalue()


def _stable_zip(raw: bytes) -> bytes:
    """openpyxl's workbook again with fixed dates on every entry (its own zip carries the time it was written)."""
    import re  # noqa: PLC0415
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries = [(i.filename, z.read(i.filename)) for i in z.infolist()]
    stamp = b"2026-11-01T00:00:00Z"                     # openpyxl writes the time of saving as "modified"
    return _zip([(n, re.sub(rb"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", stamp, d) if n == "docProps/core.xml" else d)
                 for n, d in entries])


def _workbook(sheets: list[tuple[str, list[list]]], hidden_row2: bool = False) -> bytes:
    from openpyxl import Workbook  # noqa: PLC0415
    wb = Workbook()
    wb.remove(wb.active)
    when = datetime(*FIXED)
    wb.properties.created = wb.properties.modified = when
    wb.properties.creator = wb.properties.lastModifiedBy = "EA Explorer test bench"
    for title, rows in sheets:
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
        if hidden_row2 and len(rows) > 1:
            ws.row_dimensions[2].hidden = True
    buf = io.BytesIO()
    wb.save(buf)
    return _stable_zip(buf.getvalue())


def _delivery(apps, nodes, rels, extra_app_rows: list[list] | None = None) -> bytes:
    """The Excel import format (docs/import-formats.md): row 1 names, row 2 field codes (hidden), data from row 3."""
    app_rows = [[n for _, n in APP_COLS], [c for c, _ in APP_COLS], *[list(a) for a in apps], *(extra_app_rows or [])]
    node_rows = [["Name *", "Description"], ["name", "description"], *[list(n) for n in nodes]]
    rel_rows = [["Source *", "Relationship type *", "Target *", "Name"], ["source", "relationship_type", "target", "name"],
                *[list(r) for r in rels]]
    return _workbook([("ApplicationComponent", app_rows), ("Node", node_rows), ("Relationships", rel_rows)], hidden_row2=True)


def _csv(rows: list[list]) -> bytes:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode("utf-8")


def _csv_set() -> list[tuple[str, bytes]]:
    return [
        ("master.csv", _csv([["file", "kind", "entity_type", "entity_type_name"],
                             ["applications.csv", "entities", "ApplicationComponent", "Application Component"],
                             ["technology.csv", "entities", "Node", "Node"],
                             ["relationships.csv", "relationships", "", ""]])),
        ("applications.csv", _csv([[c for c, _ in APP_COLS], *[list(a) for a in APPLICATIONS]])),
        ("technology.csv", _csv([["name", "description"], *[list(n) for n in NODES]])),
        ("relationships.csv", _csv([["source", "relationship_type", "target", "name"], *[list(r) for r in RELATIONSHIPS]])),
    ]


def _metamodel() -> bytes:
    """A small metamodel workbook in our own template's layout (services/api/eax/metamodel_workbook.py SHEETS)."""
    return _workbook([
        ("Model", [["field", "value"], ["name", f"{TAG} metamodel"], ["framework", "Self-test"], ["version", "1"],
                   ["description", "A small metamodel the self-test loads as a new model"]]),
        ("Domains", [["code", "name", "colour", "description"], ["st_business", "Self-test business", "#F5D76E", ""],
                     ["st_apps", "Self-test applications", "#9AD1F5", ""]]),
        ("Pick lists", [["code", "name", "description", "values"],
                        ["st_hosting", "Hosting", "Where it runs", "SaaS\nCloud\nOn premises"]]),
        ("Attributes", [["code", "name", "data_type", "pick_list", "unit", "description", "quality_weight"],
                        ["st_hosting", "Hosting", "pick_list", "st_hosting", "", "Where it runs", 1],
                        ["st_cost", "Yearly cost", "number", "", "EUR", "What it costs a year", 1],
                        ["st_live", "Live since", "date", "", "", "", 0]]),
        ("Types", [["code", "name", "domain", "id_prefix", "aspect", "description", "notation", "fill_colour"],
                   ["StCapability", "Self-test capability", "st_business", "STC", "behaviour", "", "", "#F5D76E"],
                   ["StApplication", "Self-test application", "st_apps", "STA", "active", "", "", "#9AD1F5"]]),
        ("Type attributes", [["type", "attribute", "required", "section", "default", "help", "quality_weight"],
                             ["StApplication", "st_hosting", "yes", "General", "Cloud", "", 1],
                             ["StApplication", "st_cost", "no", "Cost", "", "", 1],
                             ["StApplication", "st_live", "no", "General", "", "", 0]]),
        ("Relationship types", [["code", "name", "verb", "category", "directed", "description"],
                                ["st_supports", "Supports", "supports", "dependency", "yes", ""]]),
        ("Allowed relationships", [["source", "relationship", "target", "source_multiplicity", "target_multiplicity", "note"],
                                   ["StApplication", "st_supports", "StCapability", "0..*", "1..*", ""]]),
        ("Rules", [["entity_type", "attribute", "field", "rule_type", "param1", "param2", "severity", "message"],
                   ["StApplication", "st_cost", "", "min", "0", "", "error", "A cost is never below zero"]]),
    ])


def _docx(text: str) -> bytes:
    """A one-paragraph Word document (the four parts Word needs)."""
    esc = text.replace("&", "&amp;").replace("<", "&lt;")
    return _zip([
        ("[Content_Types].xml", b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
         b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
         b'<Default Extension="xml" ContentType="application/xml"/>'
         b'<Override PartName="/word/document.xml" '
         b'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'),
        ("_rels/.rels", b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
         b'Target="word/document.xml"/></Relationships>'),
        ("word/_rels/document.xml.rels", b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'),
        ("word/document.xml", ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
         f'<w:p><w:r><w:t>{esc}</w:t></w:r></w:p></w:body></w:document>').encode()),
    ])


def _pdf(text: str) -> bytes:
    """A one-page PDF with one line of text (Helvetica), its cross-reference table counted exactly."""
    esc = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 14 Tf 72 720 Td ({esc}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def _png(w: int, h: int, rgb: tuple[int, int, int]) -> bytes:
    """A plain one-colour PNG with a darker band (so a replaced image looks different)."""
    rows = b""
    for y in range(h):
        c = rgb if y < h * 2 // 3 else tuple(v // 2 for v in rgb)
        rows += b"\x00" + bytes(c) * w

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", _stored_zlib(rows)) + chunk(b"IEND", b""))


def _stored_zlib(data: bytes) -> bytes:
    """A zlib stream of stored (uncompressed) blocks, written by hand: zlib.compress gives other bytes with other zlib
    builds (zlib-ng), and the files must be the same on every machine."""
    out = bytearray(b"\x78\x01")
    for i in range(0, max(len(data), 1), 65535):
        block = data[i:i + 65535]
        last = 1 if i + 65535 >= len(data) else 0
        out += bytes([last]) + struct.pack("<HH", len(block), len(block) ^ 0xFFFF) + block
    return bytes(out + struct.pack(">I", zlib.adler32(data) & 0xFFFFFFFF))


def _json(obj) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


SURVEY = {"title": f"{TAG} survey", "description": "A short survey the self-test sends to its own test accounts",
          "sections": [{"key": "about", "title": "About the application", "questions": [
              {"key": "owner_known", "kind": "yes_no", "text": "Do you know who owns it?", "required": True},
              {"key": "hosting", "kind": "single", "text": "Where does it run?", "required": True,
               "options": [{"label": "SaaS", "value": "saas"}, {"label": "Cloud", "value": "cloud"},
                           {"label": "On premises", "value": "onprem"}]},
              {"key": "fit", "kind": "rating", "text": "How well does it fit the business?", "min": 1, "max": 5,
               "low_label": "Poorly", "high_label": "Very well"},
              {"key": "users", "kind": "number", "text": "About how many people use it?"},
              {"key": "notes", "kind": "long_text", "text": "Anything else?",
               "condition": {"question": "owner_known", "op": "equals", "value": "yes"}}]}]}

DRAWN_VIEW = f"""<mxfile host="EA Explorer" version="1"><diagram id="selftest" name="{TAG} view"><mxGraphModel><root>
<mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="a1" value="{TAG} Container Platform" style="rounded=1;whiteSpace=wrap;" vertex="1" parent="1"><mxGeometry x="40" y="40" width="200" height="60" as="geometry"/></mxCell>
<mxCell id="a2" value="{TAG} Quote Optimiser" style="rounded=1;whiteSpace=wrap;" vertex="1" parent="1"><mxGeometry x="320" y="40" width="200" height="60" as="geometry"/></mxCell>
<mxCell id="e1" value="hosts" style="endArrow=block;" edge="1" parent="1" source="a1" target="a2"><mxGeometry relative="1" as="geometry"/></mxCell>
</root></mxGraphModel></diagram></mxfile>
"""

CREDENTIALS = {
    "_comment": "Copy to a file outside the repository (or to testbench/data/credentials.json, which is ignored), fill in "
                "ONE way to sign in, and give it with --credentials <file>. Never commit a filled-in copy.",
    "token": "",
    "user": "", "password": "", "realm": "eaexplorer", "client": "eax-odata",
    "token_after_reset": "",
}


def files() -> dict[str, tuple[bytes, str, list[str]]]:
    """name -> (bytes, what it is, who uses it)."""
    good = _delivery(APPLICATIONS, NODES, RELATIONSHIPS)
    errors = _delivery(APPLICATIONS[:1], NODES, [*RELATIONSHIPS[:1], (f"{TAG} Nowhere", "Serving", f"{TAG} Quote Optimiser", "")],
                       extra_app_rows=[["", "a row with no name", "", "", "", ""],
                                       [f"{TAG} Bad Hosting", "", "", "", "Under the desk", ""],
                                       [f"{TAG} Deleted In A Delivery", "", "", "", "", "", "Yes"]])
    win = _delivery([(n, d + " (from the source)", v or "Northwind Software", ver, "Cloud", u)
                     for n, d, v, ver, _h, u in APPLICATIONS], NODES, RELATIONSHIPS)
    uploads_used = ["ui: documents journeys (upload, replace)", "api: documents writes"]
    out: dict[str, tuple[bytes, str, list[str]]] = {
        "deliveries/good.xlsx": (good, "A clean delivery in the Excel format: 3 applications, 2 nodes, 3 relationships",
                                 ["ui: deliveries journey", "api: import-sources writes"]),
        "deliveries/good-csv.zip": (_zip(_csv_set()), "The same delivery in the CSV format (master.csv and three CSVs)",
                                    ["ui: deliveries journey", "api: import-sources writes"]),
        "deliveries/with-errors.xlsx": (errors, "A delivery with problems: a row with no name, an unknown pick-list value, "
                                        "a delete (never done by a delivery) and a relationship to an unknown entity",
                                        ["ui: deliveries journey (problems shown)"]),
        "deliveries/values-win.xlsx": (win, "The good delivery again with changed values, for a source whose values win",
                                       ["ui: deliveries journey (values win)"]),
        "metamodel/metamodel.xlsx": (_metamodel(), "A small metamodel workbook (two types, three attributes, one rule)",
                                     ["ui: new model from a metamodel workbook", "api: metamodel workbook preview"]),
        "uploads/document.docx": (_docx(f"{TAG}: a Word document to upload."), "A Word document to upload", uploads_used),
        "uploads/document-v2.docx": (_docx(f"{TAG}: the Word document, second version."), "Its replacement", uploads_used),
        "uploads/document.pdf": (_pdf(f"{TAG}: a PDF to upload."), "A one-page PDF to upload", uploads_used),
        "uploads/document-v2.pdf": (_pdf(f"{TAG}: the PDF, second version."), "Its replacement", uploads_used),
        "uploads/image.png": (_png(64, 48, (40, 120, 200)), "A small image to upload (64 x 48)", uploads_used),
        "uploads/image-v2.png": (_png(64, 48, (200, 120, 40)), "Its replacement, another colour", uploads_used),
        "surveys/survey.json": (_json(SURVEY), "A survey definition: five questions, each kind once, one condition",
                                ["api: surveys writes", "ui: surveys journey"]),
        "views/drawn-view.xml": (DRAWN_VIEW.encode(), "A drawn view (draw.io XML): two shapes and a line, named as the "
                                 "delivery's entities", ["ui: drawn views journey", "api: views writes"]),
        "entities/entities.json": (_json({"entities": [
            *[{"type": "ApplicationComponent", "name": n, "description": d,
               "attributes": {"Vendor": v, "Version": ver, "Hosting": h}} for n, d, v, ver, h, _u in APPLICATIONS],
            *[{"type": "Node", "name": n, "description": d} for n, d in NODES]]}),
            "Entities with attribute values, as the API takes them", ["api: entity writes", "load: data"]),
        "entities/relationships.json": (_json({"relationships": [
            {"source": s, "type": t, "target": g, "name": n} for s, t, g, n in RELATIONSHIPS]}),
            "Relationships between those entities", ["api: relationship writes"]),
        "entities/attributes.json": (_json({"attributes": [
            {"code": "st_hosting", "name": "Hosting", "data_type": "pick_list", "values": ["SaaS", "Cloud", "On premises"]},
            {"code": "st_cost", "name": "Yearly cost", "data_type": "number", "unit": "EUR"},
            {"code": "st_live", "name": "Live since", "data_type": "date"}]}),
            "Attribute definitions (the metamodel workbook's, as JSON)", ["api: metamodel writes"]),
        "credentials.template.json": (_json(CREDENTIALS), "How to give the test bench a sign-in, with no secret in it",
                                      ["testbench: --credentials"]),
        "expected/expected.json": (_json({
            "deliveries/good.xlsx": {"new_entities": len(APPLICATIONS) + len(NODES), "new_relationships": len(RELATIONSHIPS),
                                     "problems": 0},
            "deliveries/good-csv.zip": {"new_entities": len(APPLICATIONS) + len(NODES),
                                        "new_relationships": len(RELATIONSHIPS), "problems": 0},
            "deliveries/with-errors.xlsx": {"problems_at_least": 4, "new_entities_at_most": 3},
            "deliveries/values-win.xlsx": {"changed_entities_when_values_win": len(APPLICATIONS),
                                           "changed_entities_otherwise": 0},
            "metamodel/metamodel.xlsx": {"entity_types": 2, "attributes": 3, "relationship_types": 1, "errors": 0},
            "surveys/survey.json": {"questions": 5, "sections": 1},
            "views/drawn-view.xml": {"shapes": 2, "lines": 1}}),
            "What each file should give when it is loaded", ["ui and api: the checks compare with it"]),
    }
    return out


def canonical(name: str, data: bytes) -> bytes:
    """What must stay the same: for a PNG only its picture (IHDR, IDAT, IEND), since some file stores add provenance
    chunks to PNG files they keep; every other file byte for byte."""
    if not name.endswith(".png") or not data.startswith(b"\x89PNG"):
        return data
    out, i = bytearray(data[:8]), 8
    while i + 8 <= len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        if kind in (b"IHDR", b"IDAT", b"IEND"):
            out += data[i:i + 12 + n]
        i += 12 + n
    return bytes(out)


def manifest(built: dict[str, tuple[bytes, str, list[str]]]) -> dict:
    return {"_comment": "The test data (D580): made by python -m testbench.data build; read by the outside test bench "
                        "(testbench/) and the inside self-test (EAX_TEST_DATA, /testdata in the test runner).",
            "load": "testbench/load/data.json (the load test's search words)",
            "files": {name: {"what": what, "used_by": used, "bytes": len(data), "sha256": hashlib.sha256(canonical(name, data)).hexdigest()}
                      for name, (data, what, used) in sorted(built.items())}}


def build(folder: Path = HERE) -> list[str]:
    built = files()
    written = []
    for name, (data, _w, _u) in built.items():
        p = folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists() or canonical(name, p.read_bytes()) != canonical(name, data):
            p.write_bytes(data)
            written.append(name)
    m = _json(manifest(built))
    if not (folder / "manifest.json").exists() or (folder / "manifest.json").read_bytes() != m:
        (folder / "manifest.json").write_bytes(m)
        written.append("manifest.json")
    return written


def check(folder: Path = HERE) -> list[str]:
    """The files that differ from what build() makes (empty: all as built)."""
    out = []
    for name, (data, _w, _u) in files().items():
        p = folder / name
        if not p.exists() or canonical(name, p.read_bytes()) != canonical(name, data):
            out.append(name)
    return out
