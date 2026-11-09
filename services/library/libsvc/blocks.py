"""A page is a list of simple blocks (owner, 9 Nov 2026: simple pages and tables full of links):
    {"type": "heading", "text": "..."}                      a heading
    {"type": "text", "text": "..."}                         a paragraph
    {"type": "list", "items": ["...", ...]}                 a bulleted list
    {"type": "table", "rows": [["...", ...], ...], "header": true}   a table, its first row the header when header is true
    {"type": "links", "items": [{"label": "...", "href": "..."}]}    a list of links
Text anywhere may hold links written [label](href). An href is a web address (https://, http://, mailto:) or a link into
EA Explorer: ea:model:<model>, ea:project:<project>, ea:entity:<model>:<entity>, ea:viewpoint:<model>:<code>,
ea:document:<project>:<document>, ea:canvas:<project>:<canvas>, ea:reference:<entry>, ea:page:<library>:<entry>."""

from __future__ import annotations

import re
from typing import Any

LINK = re.compile(r"\[([^\]\n]{1,300})\]\(([^)\s]{1,2000})\)")
EA = re.compile(r"^ea:(model|project|entity|viewpoint|document|canvas|reference|page):[A-Za-z0-9_.:\-]{1,200}$")
TYPES = ("heading", "text", "list", "table", "links")
MAX_BLOCKS, MAX_CELLS, MAX_TEXT = 400, 4000, 20000


class Bad(ValueError):
    pass


def good_href(href: str) -> bool:
    href = (href or "").strip()
    return bool(re.match(r"^(https?://|mailto:)\S+$", href, re.I) or EA.match(href))


def _text(v: Any, n: int = MAX_TEXT) -> str:
    s = str(v or "").replace("\r\n", "\n").strip()
    if len(s) > n:
        raise Bad("A block's text is too long.")
    for _label, href in LINK.findall(s):
        if not good_href(href):
            raise Bad(f"A link must go to a web address (https://...) or a part of EA Explorer: {href}")
    return s


def clean(blocks: Any) -> list[dict]:
    """The blocks as they are kept: only the known types and fields, every link checked."""
    if not isinstance(blocks, list):
        raise Bad("A page is a list of blocks.")
    if len(blocks) > MAX_BLOCKS:
        raise Bad("A page has too many blocks.")
    out, cells = [], 0
    for b in blocks:
        t = (b or {}).get("type")
        if t not in TYPES:
            raise Bad(f"Unknown block: {t}")
        if t in ("heading", "text"):
            s = _text(b.get("text"), 300 if t == "heading" else MAX_TEXT)
            if s:
                out.append({"type": t, "text": s})
        elif t == "list":
            items = [_text(x, 2000) for x in (b.get("items") or [])]
            items = [x for x in items if x]
            if items:
                out.append({"type": "list", "items": items})
        elif t == "table":
            rows = [[_text(c, 2000) for c in (r or [])] for r in (b.get("rows") or [])]
            rows = [r for r in rows if any(r)]
            width = max((len(r) for r in rows), default=0)
            cells += width * len(rows)
            if cells > MAX_CELLS:
                raise Bad("The tables on this page are too big.")
            if rows:
                out.append({"type": "table", "header": bool(b.get("header", True)), "rows": [r + [""] * (width - len(r)) for r in rows]})
        elif t == "links":
            items = []
            for x in b.get("items") or []:
                label, href = _text((x or {}).get("label"), 300), str((x or {}).get("href") or "").strip()
                if not href:
                    continue
                if not good_href(href):
                    raise Bad(f"A link must go to a web address (https://...) or a part of EA Explorer: {href}")
                items.append({"label": label or href, "href": href})
            if items:
                out.append({"type": "links", "items": items})
    return out


def plain(blocks: list[dict]) -> str:
    """The words of a page, for search: link labels kept, addresses left out."""
    def words(s: str) -> str:
        return LINK.sub(lambda m: m.group(1), s or "")
    out: list[str] = []
    for b in blocks or []:
        t = b.get("type")
        if t in ("heading", "text"):
            out.append(words(b.get("text")))
        elif t == "list":
            out += [words(x) for x in b.get("items") or []]
        elif t == "table":
            out += [" ".join(words(c) for c in r) for r in b.get("rows") or []]
        elif t == "links":
            out += [x.get("label") or "" for x in b.get("items") or []]
    return "\n".join(x for x in out if x)


def links(blocks: list[dict]) -> list[tuple[str, str]]:
    """Every (label, href) on a page."""
    out: list[tuple[str, str]] = []
    for b in blocks or []:
        t = b.get("type")
        texts = [b.get("text")] if t in ("heading", "text") else (b.get("items") or []) if t == "list" else \
            [c for r in b.get("rows") or [] for c in r] if t == "table" else []
        for s in texts:
            out += LINK.findall(s or "")
        if t == "links":
            out += [(x.get("label") or "", x.get("href") or "") for x in b.get("items") or []]
    return out
