"""EA Explorer's own documentation as a folder of the Enterprise library (owner, 10 Nov 2026, D550).

At every start of the library service (so also after an update, D417) the folder "EA Explorer documentation" in the
organisation's library is brought in line with the documents that ship with the running version (mounted read-only
at /data/docs, the same files the API's Documentation page shows): one sub-folder per group, one file entry per
document. A document that changed is replaced (by its content), a new one is added, and one no longer shipped is
removed; nothing else in the library is touched. People read them like any library file; the folder is the system's,
so changes made to it by hand are put back at the next start.

The grouping is the same as the API's (services/api/eax/shipped_docs.py, group_of); a test keeps the two alike.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from types import SimpleNamespace

FOLDER = "EA Explorer documentation"
SYSTEM = "system:docs"
HIDDEN = {"todo.md", "checks_raw.md"}
GROUPS = ["Getting started", "Using EA Explorer", "Administration and operations", "Command line",
          "Reference", "Release notes", "Design and decisions"]


def root() -> Path:
    # EAX_SHIPPED_DOCS, not EAX_DOCS_DIR: that one is the document store's volume in eaexplorer.env ("eax-docs",
    # /srv/eax/documents), which every container gets, so the shipped documents were looked for there (R2.0.1)
    env = os.environ.get("EAX_SHIPPED_DOCS")
    if env:
        return Path(env)
    if Path("/data/docs").is_dir():
        return Path("/data/docs")
    return Path(__file__).resolve().parents[3]


def version(base: Path) -> str:
    for p in (base / "version.toml", base / "services" / "api" / "version.toml"):
        try:
            return tomllib.loads(p.read_text(encoding="utf-8"))["version"]
        except (OSError, KeyError, tomllib.TOMLDecodeError):
            continue
    return "unknown"


def sources(base: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    if (base / "README.md").is_file():
        out.append(("readme", base / "README.md"))
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
    if (base / "releases").is_dir():
        for p in sorted((base / "releases").glob("*.md")):
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


def title_of(text: str, key: str) -> str:
    for line in text.splitlines():
        m = re.match(r"^#\s+(.+)", line)
        if m:
            return re.sub(r"[*_`]", "", m.group(1)).strip()[:200]
    if key == "command-line-help":
        return "Command line: every eax command"
    return key.replace("~", " / ").replace("-", " ").capitalize()


def plan(base: Path) -> list[dict]:
    """What the folder should hold: one item per document."""
    items = []
    for key, p in sources(base):
        try:
            data = p.read_bytes()
        except OSError:
            continue
        name = "eax-commands.txt" if key == "command-line-help" else (
            f"release-{p.stem}.md" if key.startswith("releases~") else ("README.md" if key == "readme" else key.replace("~", "-") + ".md"))
        items.append({"key": key, "group": group_of(key), "file_name": name, "content": data,
                      "title": title_of(data.decode("utf-8", "replace"), key)})
    return items


def sync(conn, base: Path | None = None) -> dict:
    """Bring the folder in line with the shipped documents. Returns what changed."""
    from . import library as L
    from .db import one, rows

    base = base or root()
    ver = version(base)
    items = plan(base)
    if not items:
        return {"version": ver, "added": 0, "changed": 0, "removed": 0, "message": "no documents shipped here"}
    who = SimpleNamespace(username=SYSTEM, roles=["super-admin"], permissions={}, library_admin=True)
    lib = L.org_library(conn)
    if not lib:
        lib = one(conn, "INSERT INTO lib.libraries (scope) VALUES ('org') RETURNING *")
    top = one(conn, """SELECT * FROM lib.folders WHERE library_id = %(l)s AND parent_id IS NULL AND name = %(n)s AND NOT is_deleted
                        ORDER BY id LIMIT 1""", l=lib["id"], n=FOLDER)
    if not top:
        L.add_folder(conn, who, lib, {"name": FOLDER})
        top = one(conn, "SELECT * FROM lib.folders WHERE library_id = %(l)s AND parent_id IS NULL AND name = %(n)s AND NOT is_deleted ORDER BY id DESC LIMIT 1",
                  l=lib["id"], n=FOLDER)
    subs = {f["name"]: f for f in rows(conn, "SELECT * FROM lib.folders WHERE parent_id = %(p)s AND NOT is_deleted", p=top["id"])}
    for g in GROUPS:
        if g not in subs and any(i["group"] == g for i in items):
            L.add_folder(conn, who, lib, {"name": g, "parent": str(top["guid"])})
            subs[g] = one(conn, "SELECT * FROM lib.folders WHERE parent_id = %(p)s AND name = %(n)s AND NOT is_deleted ORDER BY id DESC LIMIT 1",
                          p=top["id"], n=g)
    for n, g in enumerate(GROUPS):                   # the groups in reading order, not alphabetical
        if g in subs:
            conn.execute("UPDATE lib.folders SET sort_order = %(o)s WHERE id = %(i)s AND sort_order IS DISTINCT FROM %(o)s",
                         {"o": n, "i": subs[g]["id"]})
    folder_ids = [top["id"]] + [f["id"] for f in subs.values()]
    have = {(e["folder_id"], e["file_name"]): e for e in rows(conn, """SELECT * FROM lib.entries WHERE folder_id = ANY(%(f)s)
                                                                       AND kind = 'file' AND NOT is_deleted""", f=folder_ids)}
    added = changed = removed = 0
    keep = set()
    for it in items:
        f = subs[it["group"]]
        desc = f"EA Explorer {ver} documentation ({it['group']}). Refreshed from the running version at every start."
        e = have.get((f["id"], it["file_name"]))
        if not e:
            L.add_entry(conn, who, lib, {"kind": "file", "title": it["title"], "folder": str(f["guid"]), "description": desc,
                                         "tags": "ea explorer, documentation"}, file_name=it["file_name"], content=it["content"])
            added += 1
            e = one(conn, "SELECT * FROM lib.entries WHERE folder_id = %(f)s AND file_name = %(n)s AND NOT is_deleted ORDER BY id DESC LIMIT 1",
                    f=f["id"], n=it["file_name"])
        elif bytes(e["content"] or b"") != it["content"] or e["title"] != it["title"] or e["description"] != desc:
            doc = {"title": it["title"], "description": desc, "tags": e["tags"], "kind": "file",
                   "file_text": L.text_of(it["file_name"], it["content"])}
            conn.execute("""UPDATE lib.entries SET content = %(c)s, file_size = %(s)s, title = %(t)s, description = %(d)s,
                                   search_doc = %(sd)s, changed_by = %(u)s, changed_at = now() WHERE id = %(i)s""",
                         {"c": it["content"], "s": len(it["content"]), "t": it["title"], "d": desc,
                          "sd": L._search_doc(doc), "u": SYSTEM, "i": e["id"]})
            L._change(conn, lib, who, "changed", it["title"], entry=e["id"], after={"version": ver})
            changed += 1
        keep.add(e["id"])
    for e in have.values():
        if e["id"] not in keep:                      # no longer shipped with this version
            conn.execute("UPDATE lib.entries SET is_deleted = true, changed_by = %(u)s, changed_at = now() WHERE id = %(i)s",
                         {"u": SYSTEM, "i": e["id"]})
            L._change(conn, lib, who, "removed", e["title"], entry=e["id"], before={"version": ver})
            removed += 1
    return {"version": ver, "added": added, "changed": changed, "removed": removed,
            "message": f"EA Explorer {ver} documentation: {added} added, {changed} changed, {removed} removed"}


def main() -> int:
    from .db import connect
    try:
        with connect() as conn:
            out = sync(conn)
            conn.commit()
        print(f"EA Explorer library: {out['message']}", flush=True)
    except Exception as exc:  # noqa: BLE001 - the library starts even if the documents cannot be refreshed
        print(f"EA Explorer library: the documentation folder was not refreshed: {exc}", flush=True)
    return 0
