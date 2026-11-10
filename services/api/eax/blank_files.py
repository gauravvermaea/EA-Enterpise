"""Empty files to stand in for a view (owner, 9 Nov 2026): a placeholder view can be an empty Word, PowerPoint,
Excel, PDF, draw.io, Markdown or text file, put in the project's files to fill in later. Each is made here, with no
template and nothing but the placeholder's name in it (no extra libraries: Word and PowerPoint are written as the few
XML parts they need)."""

from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

TYPES = {
    "docx": "Word document",
    "pptx": "PowerPoint presentation",
    "xlsx": "Excel workbook",
    "pdf": "PDF",
    "drawio": "draw.io diagram",
    "md": "Markdown",
    "txt": "Text",
}


def file_name(name: str, file_type: str) -> str:
    stem = re.sub(r"[^\w\- .()]+", "", name or "").strip()[:80] or "Placeholder"
    return f"{stem}.{file_type}"


def make(file_type: str, name: str) -> bytes:
    """The bytes of an empty file of that type, titled with the name."""
    if file_type not in TYPES:
        raise ValueError(f"Unknown file type {file_type}: one of {', '.join(TYPES)}.")
    return {"docx": _docx, "pptx": _pptx, "xlsx": _xlsx, "pdf": _pdf, "drawio": _drawio,
            "md": lambda n: f"# {n}\n".encode(), "txt": lambda n: f"{n}\n".encode()}[file_type](name or "Placeholder")


def _zip(parts: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, xml in parts.items():          # [Content_Types].xml first
            z.writestr(path, xml)
    return buf.getvalue()


X = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"


def _rels(*rels: tuple[str, str, str]) -> str:
    return (X + f'<Relationships xmlns="{PR}">'
            + "".join(f'<Relationship Id="{i}" Type="{R}/{t}" Target="{target}"/>' for i, t, target in rels) + "</Relationships>")


def _docx(name: str) -> bytes:
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    return _zip({
        "[Content_Types].xml": X + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>",
        "_rels/.rels": _rels(("rId1", "officeDocument", "word/document.xml")),
        "word/document.xml": X + f'<w:document xmlns:w="{w}"><w:body>'
        f'<w:p><w:pPr><w:jc w:val="left"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="36"/></w:rPr><w:t xml:space="preserve">{escape(name)}</w:t></w:r></w:p>'
        "<w:p/>"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>",
    })


A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = f'xmlns:a="{A}" xmlns:r="{R}" xmlns:p="{P}"'
TREE = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')


def _theme() -> str:
    colours = (("dk1", '<a:sysClr val="windowText" lastClr="000000"/>'), ("lt1", '<a:sysClr val="window" lastClr="FFFFFF"/>'),
               ("dk2", '<a:srgbClr val="1F2937"/>'), ("lt2", '<a:srgbClr val="E5E7EB"/>'), ("accent1", '<a:srgbClr val="2563EB"/>'),
               ("accent2", '<a:srgbClr val="DC2626"/>'), ("accent3", '<a:srgbClr val="16A34A"/>'), ("accent4", '<a:srgbClr val="9333EA"/>'),
               ("accent5", '<a:srgbClr val="0891B2"/>'), ("accent6", '<a:srgbClr val="EA580C"/>'), ("hlink", '<a:srgbClr val="2563EB"/>'),
               ("folHlink", '<a:srgbClr val="7C3AED"/>'))
    fill = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    line = '<a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    font = '<a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/>'
    return (X + f'<a:theme xmlns:a="{A}" name="Blank"><a:themeElements>'
            '<a:clrScheme name="Blank">' + "".join(f"<a:{k}>{v}</a:{k}>" for k, v in colours) + "</a:clrScheme>"
            f'<a:fontScheme name="Blank"><a:majorFont>{font}</a:majorFont><a:minorFont>{font}</a:minorFont></a:fontScheme>'
            '<a:fmtScheme name="Blank">'
            f"<a:fillStyleLst>{fill * 3}</a:fillStyleLst><a:lnStyleLst>{line * 3}</a:lnStyleLst>"
            f"<a:effectStyleLst>{'<a:effectStyle><a:effectLst/></a:effectStyle>' * 3}</a:effectStyleLst>"
            f"<a:bgFillStyleLst>{fill * 3}</a:bgFillStyleLst></a:fmtScheme>"
            "</a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>")


def _pptx(name: str) -> bytes:
    title = ('<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
             '<p:spPr><a:xfrm><a:off x="609600" y="2743200"/><a:ext cx="10972800" cy="1371600"/></a:xfrm>'
             '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
             f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-GB" sz="4000" b="1"/><a:t>{escape(name)}</a:t></a:r></a:p></p:txBody></p:sp>')
    return pptx_slide(name, title)


def pptx_slide(name: str, shapes: str) -> bytes:
    """A PowerPoint file of one 16:9 slide holding the given shapes (p:sp elements, ids from 2)."""
    pml = "application/vnd.openxmlformats-officedocument.presentationml"
    return _zip({
        "[Content_Types].xml": X + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/ppt/presentation.xml" ContentType="{pml}.presentation.main+xml"/>'
        f'<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="{pml}.slideMaster+xml"/>'
        f'<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="{pml}.slideLayout+xml"/>'
        f'<Override PartName="/ppt/slides/slide1.xml" ContentType="{pml}.slide+xml"/>'
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
        "</Types>",
        "_rels/.rels": _rels(("rId1", "officeDocument", "ppt/presentation.xml")),
        "ppt/presentation.xml": X + f"<p:presentation {NS}>"
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        '<p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>'
        '<p:sldSz cx="12192000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>',
        "ppt/_rels/presentation.xml.rels": _rels(("rId1", "slideMaster", "slideMasters/slideMaster1.xml"),
                                                 ("rId2", "slide", "slides/slide1.xml"), ("rId3", "theme", "theme/theme1.xml")),
        "ppt/slideMasters/slideMaster1.xml": X + f"<p:sldMaster {NS}><p:cSld><p:bg><p:bgRef idx=\"1001\"><a:schemeClr val=\"bg1\"/></p:bgRef></p:bg>"
        f"<p:spTree>{TREE}</p:spTree></p:cSld>"
        '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" '
        'accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
        '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst></p:sldMaster>',
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": _rels(("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml"),
                                                              ("rId2", "theme", "../theme/theme1.xml")),
        "ppt/slideLayouts/slideLayout1.xml": X + f'<p:sldLayout {NS} type="blank" preserve="1"><p:cSld name="Blank"><p:spTree>{TREE}</p:spTree></p:cSld>'
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>",
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": _rels(("rId1", "slideMaster", "../slideMasters/slideMaster1.xml")),
        "ppt/slides/slide1.xml": X + f"<p:sld {NS}><p:cSld><p:spTree>{TREE}{shapes}</p:spTree></p:cSld>"
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>",
        "ppt/slides/_rels/slide1.xml.rels": _rels(("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml")),
        "ppt/theme/theme1.xml": _theme(),
    })


def _xlsx(name: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = name
    ws["A1"].font = Font(bold=True, size=14)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pdf(name: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(name)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, A4[1] - 96, name[:90])
    c.showPage()
    c.save()
    return buf.getvalue()


def _drawio(name: str) -> bytes:
    return (f'<mxfile><diagram id="placeholder" name="{escape(name, {chr(34): "&quot;"})}"><mxGraphModel><root>'
            '<mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel></diagram></mxfile>\n').encode()
