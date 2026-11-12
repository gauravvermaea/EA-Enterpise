"""EA Explorer's own documentation, for every signed-in user (owner, 10 Nov 2026, D550).

The documents are the ones that ship with the running version: the repository's `docs/` folder, `README.md`, the
command line's help (`eaxcli/help.txt`) and the release notes (`releases/`). They are mounted read-only into the API
container (docker-compose: /data/docs), so an installation always shows the documents of the version it runs; after an
update the new version's documents are there. The list builds itself from the folder: a new document appears without
a code change. A few internal working files are hidden (HIDDEN).

Markdown is turned into HTML here, safe by construction: every character of the document is HTML-escaped first, and
only then are the Markdown marks (headings, lists, tables, code, emphasis, links) turned into tags. A document that
holds `<script>` shows it as text. Links to other documents open them in the Documentation page; links out open in a
new tab; any other kind of link (javascript:, data:) stays plain text.
"""

from __future__ import annotations

import html
import os
import re
from pathlib import Path

from . import __version__

HIDDEN = {"todo.md", "checks_raw.md"}            # working notes, not documentation
GROUPS = ["Getting started", "Using EA Explorer", "Administration and operations", "Command line",
          "Reference", "Release notes", "Design and decisions"]


def root() -> Path:
    """Where the shipped documents are: EAX_SHIPPED_DOCS, else the container's /data/docs, else the repository itself."""
    # EAX_SHIPPED_DOCS, not EAX_DOCS_DIR: that one is the document store's volume in eaexplorer.env ("eax-docs",
    # /srv/eax/documents), which every container gets, so the shipped documents were looked for there (R2.0.1)
    env = os.environ.get("EAX_SHIPPED_DOCS")
    if env:
        return Path(env)
    if Path("/data/docs").is_dir():
        return Path("/data/docs")
    return Path(__file__).resolve().parents[3]                   # services/api/eax -> the repository


def _sources(base: Path) -> list[tuple[str, Path]]:
    """(key, file) for every shipped document. Keys are what the page's address uses."""
    out: list[tuple[str, Path]] = []
    readme = base / "README.md"
    if readme.is_file():
        out.append(("readme", readme))
    for p in (base / "eaxcli" / "help.txt", base / "help.txt"):
        if p.is_file():
            out.append(("command-line-help", p))
            break
    docs = base / "docs"
    if docs.is_dir():
        for p in sorted(docs.rglob("*.md")):
            rel = p.relative_to(docs).as_posix()
            if p.name in HIDDEN or rel.startswith(("requirements/", "drafts/")):
                continue
            out.append((rel[:-3].replace("/", "~"), p))
    rel_dir = base / "releases"
    if rel_dir.is_dir():
        for p in sorted(rel_dir.glob("*.md")):
            if p.name.lower() != "readme.md":
                out.append(("releases~" + p.stem, p))
    return out


def group_of(key: str) -> str:
    k = key.lower()
    if k in ("readme", "index") or k.startswith(("getting-started", "quick-start")):
        return "Getting started"
    if k.startswith("releases~"):
        return "Release notes"
    if k in ("command-line-help", "command-line-and-console"):
        return "Command line"
    if re.match(r"^(phase-|story-|design-|build-phases|decisions|capabilities-plan|architecture|database|licences)", k):
        return "Design and decisions"
    if re.match(r"^(operations|deployment|release-process|testing|backups?|security|scaling|upgrad|monitor|industry-packs)", k):
        return "Administration and operations"
    if re.match(r"^(import-formats|mcp|api|odata|metamodel|data-model|reports?)", k):
        return "Reference"
    return "Using EA Explorer"


def _title(text: str, key: str) -> str:
    for line in text.splitlines():
        m = re.match(r"^#\s+(.+)", line)
        if m:
            return re.sub(r"[*_`]", "", m.group(1)).strip()
    if key == "command-line-help":
        return "Command line: every eax command"
    return key.replace("~", " / ").replace("-", " ").capitalize()


def listing() -> dict:
    base = root()
    docs = []
    for key, p in _sources(base):
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        docs.append({"key": key, "title": _title(text, key), "group": group_of(key), "file": p.name,
                     "size": p.stat().st_size, "summary": _summary(text)})
    order = {g: i for i, g in enumerate(GROUPS)}
    docs.sort(key=lambda d: (order.get(d["group"], 99), d["key"] != "readme", d["title"].lower()))
    return {"version": __version__, "groups": GROUPS, "documents": docs}


def _summary(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith(("#", "|", "```", "-", "*", ">")):
            s = re.sub(r"[*_`]|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", s)
            return s[:220]
    return ""


def find(key: str) -> tuple[str, Path]:
    for k, p in _sources(root()):
        if k == key:
            return k, p
    raise LookupError(f"No document {key}.")


def document(key: str) -> dict:
    k, p = find(key)
    text = p.read_text(encoding="utf-8")
    body = ("<pre class=\"doc-help\">" + html.escape(text) + "</pre>") if k == "command-line-help" else render(text)
    return {"key": k, "title": _title(text, k), "group": group_of(k), "file": p.name, "version": __version__,
            "html": body, "size": p.stat().st_size}


def raw(key: str) -> tuple[str, bytes]:
    _k, p = find(key)
    return p.name, p.read_bytes()


def search(q: str, limit: int = 40) -> list[dict]:
    words = [w for w in re.split(r"\s+", (q or "").lower().strip()) if w]
    if not words:
        return []
    out = []
    for k, p in _sources(root()):
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        low = text.lower()
        if not all(w in low for w in words):
            continue
        hits = sum(low.count(w) for w in words)
        i = low.find(words[0])
        snippet = text[max(0, i - 80): i + 160].replace("\n", " ")
        out.append({"key": k, "title": _title(text, k), "group": group_of(k), "hits": hits, "snippet": snippet.strip()})
    out.sort(key=lambda d: -d["hits"])
    return out[:limit]


# ---------------------------------------------------------------- Markdown to safe HTML
_SAFE_SCHEMES = ("http://", "https://", "mailto:")


def _href(target: str) -> tuple[str, bool] | None:
    """(href, external) for a Markdown link target, or None when it must stay text."""
    t = html.unescape(target.strip())
    if t.startswith("<") and t.endswith(">"):
        t = t[1:-1]
    if t.lower().startswith(_SAFE_SCHEMES):
        return t, True
    if t.startswith("#"):
        return "#doc-" + re.sub(r"[^a-z0-9-]", "", t[1:].lower()), False
    if re.match(r"^[a-z][a-z0-9+.-]*:", t, re.I):
        return None                                            # javascript:, data:, file:, ea: and the like
    path, _, anchor = t.partition("#")
    name = path.split("/")[-1]
    if name.lower() == "readme.md":
        key = "readme"
    elif name.lower().endswith(".md"):
        if "releases/" in path:
            key = "releases~" + name[:-3]
        else:
            key = re.sub(r"^(\.\./)*(docs/)?", "", path)[:-3].replace("/", "~")
    elif name == "help.txt":
        key = "command-line-help"
    else:
        return None                                            # other files of the repository are not served
    return "#/documentation/" + key + (("?at=" + anchor) if anchor else ""), False


def _inline(s: str) -> str:
    """s is already HTML-escaped; turn the inline Markdown marks into tags."""
    codes: list[str] = []

    def keep_code(m):
        codes.append("<code>" + m.group(1) + "</code>")
        return f"\x00{len(codes) - 1}\x00"
    s = re.sub(r"`([^`]+)`", keep_code, s)

    def link(m):
        text, target = m.group(1), m.group(2)
        h = _href(target)
        if not h:
            return text
        href, external = h
        attr = ' target="_blank" rel="noopener noreferrer"' if external else ""
        return f'<a href="{html.escape(href, quote=True)}"{attr}>{text}</a>'
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)", link, s)
    s = re.sub(r"(?<![\"'=/>])\b(https?://[^\s<)]+)", lambda m: f'<a href="{m.group(1)}" target="_blank" rel="noopener noreferrer">{m.group(1)}</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"(?<![\w_])_([^_\n]+)_(?![\w_])", r"<em>\1</em>", s)
    s = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], s)


def _anchor(text: str) -> str:
    return "doc-" + re.sub(r"[^a-z0-9]+", "-", html.unescape(re.sub(r"<[^>]+>", "", text)).lower()).strip("-")


def _cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)]


def render(text: str) -> str:
    """Markdown to HTML. Every character is escaped before any tag is made, so nothing in a document runs."""
    lines = html.escape(text, quote=True).replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    para: list[str] = []

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(x.strip() for x in para)) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*```", line):                       # code block
            flush()
            i += 1
            code = []
            while i < len(lines) and not re.match(r"^\s*```", lines[i]):
                code.append(lines[i])
                i += 1
            out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            flush()
            n = len(m.group(1))
            body = _inline(m.group(2))
            out.append(f'<h{n} id="{_anchor(body)}">{body}</h{n}>')
            i += 1
            continue
        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", line):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            flush()
            head = _cells(line)
            i += 2
            body = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                body.append(_cells(lines[i]))
                i += 1
            t = ["<div class=\"doc-table\"><table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead><tbody>"]
            for r in body:
                t.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
            out.append("".join(t) + "</tbody></table></div>")
            continue
        if line.startswith("&gt;"):
            flush()
            quote = []
            while i < len(lines) and lines[i].startswith("&gt;"):
                quote.append(re.sub(r"^&gt;\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>" + render_escaped(quote) + "</blockquote>")
            continue
        if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
            flush()
            i = _list(lines, i, out)
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        para.append(line)
        i += 1
    flush()
    return "\n".join(out)


def render_escaped(lines: list[str]) -> str:
    """render() for lines that are already escaped (a quote's inside)."""
    return render(html.unescape("\n".join(lines)))


def _list(lines: list[str], i: int, out: list[str]) -> int:
    """A list, nested by indentation. Returns the line after it."""
    stack: list[tuple[int, str]] = []                          # (indent, "ul"|"ol")
    item: list[str] = []

    def close_item():
        if item:
            out.append("<li>" + _inline(" ".join(x.strip() for x in item)) + "</li>")
            item.clear()

    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if m:
            indent, kind = len(m.group(1).replace("\t", "    ")), ("ol" if m.group(2)[0].isdigit() else "ul")
            close_item()
            if not stack or indent > stack[-1][0]:
                out.append(f"<{kind}>")
                stack.append((indent, kind))
            else:
                while stack and indent < stack[-1][0]:
                    out.append(f"</{stack.pop()[1]}>")
                if not stack:
                    out.append(f"<{kind}>")
                    stack.append((indent, kind))
            item.append(m.group(3))
            i += 1
            continue
        if line.strip() and stack and (line.startswith(" ") or line.startswith("\t")):
            item.append(line)                                  # an item carried on to the next line
            i += 1
            continue
        break
    close_item()
    while stack:
        out.append(f"</{stack.pop()[1]}>")
    return i
