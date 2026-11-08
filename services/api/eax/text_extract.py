"""The text inside a file, for search (the reference library, D299). Best effort: a file it cannot read gives ''.

PDF (pypdf), Word (.docx), PowerPoint (.pptx), Excel (.xlsx), OpenDocument (.odt, .ods, .odp) and plain text (txt, md,
csv, json, xml, html). Office files are zip files of XML: their text is read out of the XML, nothing is run. A
scanned PDF has no text to read (no OCR here)."""

from __future__ import annotations

import html
import io
import re
import zipfile

LIMIT = 500_000                 # characters kept per file
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def _clean(s: str) -> str:
    return _SPACE.sub(" ", s).strip()[:LIMIT]


def _xml_text(xml: str, tags: tuple[str, ...]) -> str:
    out = []
    for t in tags:
        out += re.findall(rf"<{t}(?:\s[^>]*)?>(.*?)</{t}>", xml, re.S)
    return " ".join(html.unescape(_TAG.sub(" ", x)) for x in out)


def _zip_parts(content: bytes, pattern: str) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(pattern, n))
        total, out = 0, []
        for n in names:
            info = z.getinfo(n)
            if info.file_size > 50_000_000 or total > 200_000_000:     # a zip bomb is not read
                break
            total += info.file_size
            out.append(z.read(n).decode("utf-8", "replace"))
        return out


def _pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:                     # pragma: no cover (in the image)
        return ""
    r = PdfReader(io.BytesIO(content))
    parts, n = [], 0
    for page in r.pages:
        t = page.extract_text() or ""
        parts.append(t)
        n += len(t)
        if n > LIMIT:
            break
    return " ".join(parts)


def text_of(file_name: str, content: bytes) -> str:
    ext = (file_name.rsplit(".", 1)[-1] if "." in file_name else "").lower()
    try:
        if ext == "pdf":
            return _clean(_pdf(content))
        if ext in ("docx", "docm", "dotx"):
            return _clean(" ".join(_xml_text(x, ("w:t",)) for x in _zip_parts(content, r"word/(document|header\d*|footer\d*|footnotes)\.xml")))
        if ext in ("pptx", "potx"):
            return _clean(" ".join(_xml_text(x, ("a:t",)) for x in _zip_parts(content, r"ppt/(slides/slide\d+|notesSlides/notesSlide\d+)\.xml")))
        if ext in ("xlsx", "xlsm"):
            return _clean(" ".join(_xml_text(x, ("t",)) for x in _zip_parts(content, r"xl/sharedStrings\.xml")))
        if ext in ("odt", "ods", "odp"):
            return _clean(" ".join(html.unescape(_TAG.sub(" ", x)) for x in _zip_parts(content, r"content\.xml")))
        if ext in ("txt", "md", "csv", "json", "xml", "yaml", "yml", "log"):
            return _clean(content[: LIMIT * 4].decode("utf-8", "replace"))
        if ext in ("html", "htm"):
            s = content[: LIMIT * 4].decode("utf-8", "replace")
            s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
            return _clean(html.unescape(_TAG.sub(" ", s)))
    except Exception:                       # a damaged or odd file: no text, the file is still kept
        return ""
    return ""
