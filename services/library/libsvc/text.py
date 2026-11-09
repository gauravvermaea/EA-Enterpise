"""The words inside an uploaded file, for search: PDF, Word (.docx), PowerPoint (.pptx), and plain text."""

from __future__ import annotations

import io
import re
import zipfile


def text_of(file_name: str, content: bytes, limit: int = 200_000) -> str:
    name = (file_name or "").lower()
    try:
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            r = PdfReader(io.BytesIO(content))
            return " ".join((p.extract_text() or "") for p in r.pages[:200])[:limit]
        if name.endswith((".docx", ".pptx", ".xlsx")):
            z = zipfile.ZipFile(io.BytesIO(content))
            parts = [n for n in z.namelist() if n.endswith(".xml") and re.match(r"^(word/document|ppt/slides/slide\d+|xl/sharedStrings)", n)]
            xml = " ".join(z.read(n).decode("utf-8", "ignore") for n in parts)
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()[:limit]
        if name.endswith((".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml")):
            return re.sub(r"<[^>]+>", " ", content.decode("utf-8", "ignore"))[:limit]
    except Exception:  # noqa: BLE001 - a file that cannot be read is still kept; only its name is searched
        return ""
    return ""
