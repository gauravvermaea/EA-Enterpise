"""The library's rules (phase 15.2, owner, 9 Nov 2026, D346 to D350). Keep it simple:

    libraries     the organisation's (enterprise) library, and one per project (made the first time it is opened)
    who changes   the enterprise library: anyone signed in; a project library: anyone on the project (not while it is
                  frozen). Changes show at once (D349); every change is kept with its before and after and can be
                  undone: Library Admins and Super Admins undo in the enterprise library, a project's admins in theirs
    folders       a tree of any shape; entries are pages (simple blocks), links and the occasional file
    in enterprise a project admin shows the project library in the enterprise library (read only, D350), or points the
                  project at a library of its own elsewhere (an address its Library tab opens)
    search        one box: titles, descriptions, tags, the words of pages, link names, the text inside files and
                  folder names, whole words and the start of words, with a short excerpt
Rules are here, never in the database (D248).
"""

from __future__ import annotations

import json
import mimetypes
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from . import blocks as bk
from . import main_api
from .config import get_settings
from .db import one, rows
from .text import text_of

EDIT_HOLD = timedelta(minutes=30)       # a page held for editing is free again after this long


class Refused(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _clean(s: Any, n: int = 300) -> str:
    return " ".join(str(s or "").split())[:n]


def _tags(v: Any) -> list[str]:
    if isinstance(v, str):
        v = v.split(",")
    return sorted({_clean(t, 60).lower() for t in v or [] if _clean(t, 60)})[:30]


# ---------------------------------------------------------------- libraries and what someone may do there
def org_library(conn) -> dict:
    return one(conn, "SELECT * FROM lib.libraries WHERE scope = 'org'")


def project_library(conn, person, project_id: str) -> tuple[dict, dict]:
    """The project's library (made the first time), with the project as this person sees it."""
    p = main_api.project(person, project_id)
    lib = one(conn, "SELECT * FROM lib.libraries WHERE project_guid = %(g)s::uuid", g=p["id"])
    if not lib:
        lib = one(conn, """INSERT INTO lib.libraries (scope, project_guid, project_name, created_by) VALUES ('project', %(g)s::uuid, %(n)s, %(u)s)
                           ON CONFLICT (project_guid) DO UPDATE SET project_name = EXCLUDED.project_name RETURNING *""",
                  g=p["id"], n=p["name"], u=person.username)
    elif p["name"] and p["name"] != lib["project_name"]:
        lib = one(conn, "UPDATE lib.libraries SET project_name = %(n)s WHERE id = %(i)s RETURNING *", n=p["name"], i=lib["id"])
    return lib, p


def library(conn, person, lib_id: str) -> tuple[dict, dict]:
    """A library by id with what this person may do there: read, write, admin."""
    lib = one(conn, "SELECT * FROM lib.libraries WHERE guid::text = %(g)s", g=str(lib_id))
    if not lib:
        raise Refused("No such library.", 404)
    return lib, may(conn, person, lib)


def may(conn, person, lib: dict) -> dict:
    if lib["scope"] == "org":
        return {"read": True, "write": True, "admin": person.library_admin}
    try:
        p = main_api.project(person, str(lib["project_guid"]))
    except main_api.Refused as exc:
        if exc.status in (403, 404) and lib["in_enterprise"]:
            return {"read": True, "write": False, "admin": False}      # shown in the enterprise library: everyone reads it
        raise
    member = bool(p["my_roles"]) or p["may_contribute"] or "super-admin" in person.roles
    return {"read": True, "write": member and not p["frozen"], "admin": (p["may_admin"] or "super-admin" in person.roles) and not p["frozen"],
            "project": p}


def need(rights: dict, what: str) -> None:
    if not rights.get(what):
        raise Refused({"write": "Only the project's people change its library." if "project" in rights else "Not allowed.",
                       "admin": "Needs a Library Admin or a Super Admin (a project's Project Admin for its library)."}.get(what, "Not allowed."), 403)


# ---------------------------------------------------------------- folders
def tree(conn, lib: dict) -> list[dict]:
    fs = rows(conn, """SELECT guid::text AS id, name, parent_id, id AS _id, sort_order FROM lib.folders
                        WHERE library_id = %(l)s AND NOT is_deleted ORDER BY sort_order, lower(name)""", l=lib["id"])
    by = {f["_id"]: f["id"] for f in fs}
    counts = {r["folder_id"]: r["n"] for r in rows(conn, """SELECT folder_id, count(*) AS n FROM lib.entries WHERE library_id = %(l)s
                                                              AND NOT is_deleted GROUP BY folder_id""", l=lib["id"])}
    return [{"id": f["id"], "name": f["name"], "parent": by.get(f["parent_id"]), "entries": counts.get(f["_id"], 0)} for f in fs]


def _folder(conn, lib: dict, fid: str | None) -> dict | None:
    if not fid:
        return None
    f = one(conn, "SELECT * FROM lib.folders WHERE library_id = %(l)s AND guid::text = %(g)s AND NOT is_deleted", l=lib["id"], g=str(fid))
    if not f:
        raise Refused("No such folder in this library.", 404)
    return f


def add_folder(conn, person, lib: dict, data: dict) -> dict:
    name = _clean(data.get("name"), 120)
    if not name:
        raise Refused("Name the folder.")
    parent = _folder(conn, lib, data.get("parent"))
    f = one(conn, """INSERT INTO lib.folders (library_id, parent_id, name, created_by) VALUES (%(l)s, %(p)s, %(n)s, %(u)s) RETURNING *""",
            l=lib["id"], p=parent["id"] if parent else None, n=name, u=person.username)
    _change(conn, lib, person, "added", name, folder=f["id"], after={"folder": name})
    return {"id": str(f["guid"]), "message": f"Folder {name} made."}


def change_folder(conn, person, lib: dict, fid: str, data: dict) -> dict:
    f = _folder(conn, lib, fid)
    name = _clean(data.get("name", f["name"]), 120)
    parent_id = f["parent_id"]
    if "parent" in data:
        parent = _folder(conn, lib, data.get("parent"))
        parent_id = parent["id"] if parent else None
        p = parent_id
        while p:                                         # not into itself or one of its own folders
            if p == f["id"]:
                raise Refused("A folder cannot go inside itself.")
            p = (one(conn, "SELECT parent_id FROM lib.folders WHERE id = %(i)s", i=p) or {}).get("parent_id")
    if not name:
        raise Refused("Name the folder.")
    conn.execute("UPDATE lib.folders SET name = %(n)s, parent_id = %(p)s WHERE id = %(i)s", {"n": name, "p": parent_id, "i": f["id"]})
    _change(conn, lib, person, "changed", name, folder=f["id"], before={"folder": f["name"], "parent": f["parent_id"]},
            after={"folder": name, "parent": parent_id})
    return {"id": fid, "message": "Folder saved."}


def remove_folder(conn, person, lib: dict, fid: str) -> dict:
    """The folder and what is in it go (they can be undone, from Recent changes)."""
    f = _folder(conn, lib, fid)
    ids = [f["id"]]
    for x in ids:
        ids += [r["id"] for r in rows(conn, "SELECT id FROM lib.folders WHERE parent_id = %(p)s AND NOT is_deleted", p=x)]
    conn.execute("UPDATE lib.folders SET is_deleted = true WHERE id = ANY(%(i)s)", {"i": ids})
    n = conn.execute("UPDATE lib.entries SET is_deleted = true, changed_by = %(u)s, changed_at = now() WHERE folder_id = ANY(%(i)s) AND NOT is_deleted",
                     {"i": ids, "u": person.username}).rowcount
    _change(conn, lib, person, "removed", f["name"], folder=f["id"], before={"folder": f["name"], "folders": ids})
    return {"id": fid, "message": f"Folder {f['name']} removed, with {n} entr{'y' if n == 1 else 'ies'} (undo from Recent changes)."}


# ---------------------------------------------------------------- entries
def _search_doc(e: dict) -> str:
    parts = [e.get("title"), e.get("description"), " ".join(e.get("tags") or [])]
    if e.get("kind") == "page":
        parts.append(bk.plain(e.get("blocks") or []))
    elif e.get("kind") == "link":
        parts.append(e.get("href") if str(e.get("href") or "").startswith("http") else "")
    elif e.get("kind") == "file":
        parts += [e.get("file_name"), e.get("file_text") or ""]
    return "\n".join(str(p) for p in parts if p)[:400_000]


def _snapshot(e: dict) -> dict:
    return {k: (e.get(k) if not isinstance(e.get(k), datetime) else e[k].isoformat()) for k in
            ("title", "description", "tags", "blocks", "href", "folder_id", "file_name")}


def _change(conn, lib: dict, person, action: str, title: str, entry: int | None = None, folder: int | None = None,
            before: dict | None = None, after: dict | None = None) -> None:
    conn.execute("""INSERT INTO lib.changes (library_id, entry_id, folder_id, action, title, before, after, username)
                    VALUES (%(l)s, %(e)s, %(f)s, %(a)s, %(t)s, %(b)s, %(af)s, %(u)s)""",
                 {"l": lib["id"], "e": entry, "f": folder, "a": action, "t": title[:300], "b": json.dumps(before) if before is not None else None,
                  "af": json.dumps(after) if after is not None else None, "u": person.username})


def _entry(conn, lib: dict | None, eid: str) -> dict:
    e = one(conn, "SELECT * FROM lib.entries WHERE guid::text = %(g)s AND NOT is_deleted" + (" AND library_id = %(l)s" if lib else ""),
            g=str(eid), l=lib["id"] if lib else None)
    if not e:
        raise Refused("No such entry in this library.", 404)
    return e


def entries(conn, lib: dict, fid: str | None) -> dict:
    f = _folder(conn, lib, fid)
    es = rows(conn, f"""SELECT guid::text AS id, kind, title, description, tags, href, file_name, file_size, changed_by, changed_at,
                               created_by, created_at FROM lib.entries
                         WHERE library_id = %(l)s AND NOT is_deleted AND folder_id {"= %(f)s" if f else "IS NULL"}
                         ORDER BY sort_order, lower(title)""", l=lib["id"], f=f["id"] if f else None)
    return {"folder": {"id": str(f["guid"]), "name": f["name"]} if f else None, "path": _path(conn, f), "entries": es}


def _path(conn, f: dict | None) -> list[dict]:
    out = []
    while f:
        out.insert(0, {"id": str(f["guid"]), "name": f["name"]})
        f = one(conn, "SELECT * FROM lib.folders WHERE id = %(i)s", i=f["parent_id"]) if f["parent_id"] else None
    return out


def get_entry(conn, lib: dict, eid: str) -> dict:
    e = _entry(conn, lib, eid)
    f = one(conn, "SELECT * FROM lib.folders WHERE id = %(i)s", i=e["folder_id"]) if e["folder_id"] else None
    hold = e["editing_by"] if e["editing_by"] and e["editing_at"] and datetime.now(UTC) - e["editing_at"] < EDIT_HOLD else ""
    return {"id": str(e["guid"]), "kind": e["kind"], "title": e["title"], "description": e["description"], "tags": e["tags"],
            "blocks": e["blocks"], "href": e["href"], "file_name": e["file_name"], "file_size": e["file_size"],
            "content_type": e["content_type"], "folder": str(f["guid"]) if f else None, "path": _path(conn, f),
            "editing_by": hold, "created_by": e["created_by"], "created_at": e["created_at"], "changed_by": e["changed_by"],
            "changed_at": e["changed_at"]}


def _fields(data: dict, kind: str) -> dict:
    out: dict[str, Any] = {"title": _clean(data.get("title"), 300), "description": _clean(data.get("description"), 2000),
                           "tags": _tags(data.get("tags"))}
    if not out["title"]:
        raise Refused("Give it a title.")
    try:
        if kind == "page":
            out["blocks"] = bk.clean(data.get("blocks") or [])
        elif kind == "link":
            href = str(data.get("href") or "").strip()
            if not bk.good_href(href):
                raise Refused("A link goes to a web address (https://...) or a part of EA Explorer.")
            out["href"] = href
    except bk.Bad as exc:
        raise Refused(str(exc)) from None
    return out


def add_entry(conn, person, lib: dict, data: dict, file_name: str = "", content: bytes = b"") -> dict:
    kind = data.get("kind") or ("file" if content else "page")
    if kind not in ("page", "link", "file"):
        raise Refused("An entry is a page, a link or a file.")
    if kind == "file":
        if not content:
            raise Refused("Choose a file to upload.")
        if len(content) > get_settings().max_file_mb * 1024 * 1024:
            raise Refused(f"A file in the library is at most {get_settings().max_file_mb} MB: link to large documents instead.", 413)
        data = {**data, "title": data.get("title") or file_name}
    f = _folder(conn, lib, data.get("folder"))
    v = _fields(data, kind)
    doc = {**v, "kind": kind, "file_name": file_name, "file_text": text_of(file_name, content) if content else ""}
    e = one(conn, """INSERT INTO lib.entries (library_id, folder_id, kind, title, description, tags, blocks, href, file_name, content_type,
                                              content, file_size, search_doc, created_by, changed_by, changed_at)
                     VALUES (%(l)s, %(f)s, %(k)s, %(t)s, %(d)s, %(tg)s, %(b)s, %(h)s, %(fn)s, %(ct)s, %(c)s, %(fs)s, %(s)s, %(u)s, %(u)s, now())
                     RETURNING *""",
            l=lib["id"], f=f["id"] if f else None, k=kind, t=v["title"], d=v["description"], tg=v["tags"], b=json.dumps(v.get("blocks", [])),
            h=v.get("href", ""), fn=file_name if content else "", ct=(mimetypes.guess_type(file_name)[0] or "application/octet-stream") if content else "",
            c=content or None, fs=len(content or b""), s=_search_doc(doc), u=person.username)
    _change(conn, lib, person, "added", v["title"], entry=e["id"], after=_snapshot(e))
    return {"id": str(e["guid"]), "message": f"{v['title']} added."}


def change_entry(conn, person, lib: dict, eid: str, data: dict) -> dict:
    e = _entry(conn, lib, eid)
    if e["kind"] == "page" and "blocks" in data and _held_by_other(e, person):
        raise Refused(f"{e['editing_by']} is editing this page; try again when they are done.", 409)
    merged = {"title": data.get("title", e["title"]), "description": data.get("description", e["description"]),
              "tags": data.get("tags", e["tags"]), "blocks": data.get("blocks", e["blocks"]), "href": data.get("href", e["href"])}
    v = _fields(merged, e["kind"])
    folder_id = e["folder_id"]
    if "folder" in data:
        f = _folder(conn, lib, data.get("folder"))
        folder_id = f["id"] if f else None
    file_text = text_of(e["file_name"], bytes(e["content"])) if e["kind"] == "file" and e["content"] else ""
    after = {**e, **v, "folder_id": folder_id}
    conn.execute("""UPDATE lib.entries SET title = %(t)s, description = %(d)s, tags = %(tg)s, blocks = %(b)s, href = %(h)s, folder_id = %(f)s,
                           search_doc = %(s)s, changed_by = %(u)s, changed_at = now(), editing_by = '', editing_at = NULL WHERE id = %(i)s""",
                 {"t": v["title"], "d": v["description"], "tg": v["tags"], "b": json.dumps(v.get("blocks", e["blocks"])), "h": v.get("href", e["href"]),
                  "f": folder_id, "s": _search_doc({**after, "file_text": file_text}), "u": person.username, "i": e["id"]})
    _change(conn, lib, person, "moved" if folder_id != e["folder_id"] and set(data) == {"folder"} else "changed", v["title"],
            entry=e["id"], before=_snapshot(e), after=_snapshot(after))
    return {"id": eid, "message": f"{v['title']} saved."}


def remove_entry(conn, person, lib: dict, eid: str) -> dict:
    e = _entry(conn, lib, eid)
    conn.execute("UPDATE lib.entries SET is_deleted = true, changed_by = %(u)s, changed_at = now() WHERE id = %(i)s", {"u": person.username, "i": e["id"]})
    _change(conn, lib, person, "removed", e["title"], entry=e["id"], before=_snapshot(e))
    return {"id": eid, "message": f"{e['title']} removed (undo from Recent changes)."}


def _held_by_other(e: dict, person) -> bool:
    return bool(e["editing_by"] and e["editing_by"] != person.username and e["editing_at"]
                and datetime.now(UTC) - e["editing_at"] < EDIT_HOLD)


def hold(conn, person, lib: dict, eid: str, on: bool) -> dict:
    """A page is held while someone edits it (others see who); let go on saving or cancelling, or after 30 minutes."""
    e = _entry(conn, lib, eid)
    if on and _held_by_other(e, person):
        raise Refused(f"{e['editing_by']} is editing this page.", 409)
    conn.execute("UPDATE lib.entries SET editing_by = %(u)s, editing_at = %(t)s WHERE id = %(i)s",
                 {"u": person.username if on else "", "t": datetime.now(UTC) if on else None, "i": e["id"]})
    return {"id": eid, "editing_by": person.username if on else ""}


def file_of(conn, lib: dict, eid: str) -> tuple[bytes, str, str]:
    e = _entry(conn, lib, eid)
    if e["kind"] != "file" or e["content"] is None:
        raise Refused("Not a file.", 404)
    return bytes(e["content"]), e["file_name"], e["content_type"] or "application/octet-stream"


# ---------------------------------------------------------------- history and undo
def history(conn, lib: dict, eid: str | None = None, limit: int = 100) -> list[dict]:
    cond = "c.library_id = %(l)s" + (" AND e.guid::text = %(e)s" if eid else "")
    return rows(conn, f"""SELECT c.id, c.action, c.title, c.username, c.at, c.undone_by, e.guid::text AS entry, f.guid::text AS folder,
                                 c.before IS NOT NULL AS has_before
                            FROM lib.changes c LEFT JOIN lib.entries e ON e.id = c.entry_id LEFT JOIN lib.folders f ON f.id = c.folder_id
                           WHERE {cond} ORDER BY c.at DESC, c.id DESC LIMIT %(n)s""", l=lib["id"], e=str(eid or ""), n=limit)


def change_detail(conn, lib: dict, cid: int) -> dict:
    c = one(conn, "SELECT * FROM lib.changes WHERE id = %(i)s AND library_id = %(l)s", i=int(cid), l=lib["id"])
    if not c:
        raise Refused("No such change.", 404)
    return {"id": c["id"], "action": c["action"], "title": c["title"], "username": c["username"], "at": c["at"],
            "before": c["before"], "after": c["after"], "undone_by": c["undone_by"]}


def undo(conn, person, lib: dict, cid: int) -> dict:
    """Puts back what was there before a change: an added entry or folder goes, a removed one comes back, a changed one
    gets its earlier title, text and place. The undo is itself a change (and can be undone)."""
    c = one(conn, "SELECT * FROM lib.changes WHERE id = %(i)s AND library_id = %(l)s", i=int(cid), l=lib["id"])
    if not c:
        raise Refused("No such change.", 404)
    if c["undone_by"]:
        raise Refused(f"{c['undone_by']} undid this change already.", 409)
    if c["folder_id"]:
        if c["action"] == "added":
            conn.execute("UPDATE lib.folders SET is_deleted = true WHERE id = %(i)s", {"i": c["folder_id"]})
        elif c["action"] == "removed":
            ids = (c["before"] or {}).get("folders") or [c["folder_id"]]
            conn.execute("UPDATE lib.folders SET is_deleted = false WHERE id = ANY(%(i)s)", {"i": ids})
            conn.execute("""UPDATE lib.entries SET is_deleted = false WHERE folder_id = ANY(%(i)s) AND is_deleted
                             AND changed_at >= %(t)s - interval '5 seconds'""", {"i": ids, "t": c["at"]})
        elif c["before"]:
            conn.execute("UPDATE lib.folders SET name = %(n)s, parent_id = %(p)s WHERE id = %(i)s",
                         {"n": c["before"]["folder"], "p": c["before"].get("parent"), "i": c["folder_id"]})
    elif c["entry_id"]:
        e = one(conn, "SELECT * FROM lib.entries WHERE id = %(i)s", i=c["entry_id"])
        if c["action"] == "added":
            conn.execute("UPDATE lib.entries SET is_deleted = true WHERE id = %(i)s", {"i": e["id"]})
        elif c["action"] == "removed":
            conn.execute("UPDATE lib.entries SET is_deleted = false WHERE id = %(i)s", {"i": e["id"]})
        elif c["before"]:
            b = c["before"]
            doc = {**e, **b, "file_text": text_of(e["file_name"], bytes(e["content"])) if e["content"] else ""}
            conn.execute("""UPDATE lib.entries SET title = %(t)s, description = %(d)s, tags = %(tg)s, blocks = %(b)s, href = %(h)s,
                                   folder_id = %(f)s, search_doc = %(s)s, changed_by = %(u)s, changed_at = now() WHERE id = %(i)s""",
                         {"t": b["title"], "d": b["description"], "tg": b["tags"], "b": json.dumps(b.get("blocks") or []), "h": b.get("href") or "",
                          "f": b.get("folder_id"), "s": _search_doc(doc), "u": person.username, "i": e["id"]})
    conn.execute("UPDATE lib.changes SET undone_by = %(u)s WHERE id = %(i)s", {"u": person.username, "i": c["id"]})
    _change(conn, lib, person, "undone", f"{c['title']} ({c['action']} by {c['username']})", entry=c["entry_id"], folder=c["folder_id"])
    return {"id": c["id"], "message": f"Undone: {c['title']} is as it was before {c['username']}'s change."}


# ---------------------------------------------------------------- search
def _tsquery(q: str) -> str:
    """Every word, whole or the start of it: "cap map" -> cap:* & map:*."""
    return " & ".join(f"{w}:*" for w in re.findall(r"\w+", q.lower())[:12])


def search(conn, libs: list[dict], q: str, limit: int = 60) -> dict:
    """Entries and folders in these libraries that match: every word, whole or the start of it; best first, with an
    excerpt. A word that matches nothing as a word is also looked for inside words (partial)."""
    q = (q or "").strip()
    if len(q) < 2 or not libs:
        return {"q": q, "results": [], "folders": []}
    ids = [lb["id"] for lb in libs]
    names = {lb["id"]: ("Enterprise library" if lb["scope"] == "org" else lb["project_name"]) for lb in libs}
    tsq = _tsquery(q)
    found = rows(conn, """
        SELECT e.guid::text AS id, e.kind, e.title, e.description, e.href, e.file_name, e.library_id, l.guid::text AS library,
               f.guid::text AS folder, f.name AS folder_name,
               ts_rank(to_tsvector('simple', e.search_doc), to_tsquery('simple', %(q)s)) AS rank,
               ts_headline('simple', coalesce(nullif(substr(e.search_doc, length(e.title) + 2), ''), e.search_doc), to_tsquery('simple', %(q)s),
                           'MaxWords=24, MinWords=8, ShortWord=2, MaxFragments=1, StartSel=<<, StopSel=>>') AS excerpt
          FROM lib.entries e JOIN lib.libraries l ON l.id = e.library_id LEFT JOIN lib.folders f ON f.id = e.folder_id
         WHERE e.library_id = ANY(%(l)s) AND NOT e.is_deleted AND %(q)s <> ''
           AND to_tsvector('simple', e.search_doc) @@ to_tsquery('simple', %(q)s)
         ORDER BY (lower(e.title) LIKE lower(%(like)s)) DESC, rank DESC, lower(e.title) LIMIT %(n)s""",
                 q=tsq, l=ids, like=f"%{q}%", n=limit) if tsq else []
    if len(found) < 5:                                       # partial words: "archi" finds "enterprise-architecture"
        seen = {r["id"] for r in found}
        found += [r for r in rows(conn, """
            SELECT e.guid::text AS id, e.kind, e.title, e.description, e.href, e.file_name, e.library_id, l.guid::text AS library,
                   f.guid::text AS folder, f.name AS folder_name, similarity(e.search_doc, %(q)s) AS rank,
                   substr(e.search_doc, greatest(1, strpos(lower(e.search_doc), lower(%(w)s)) - 60), 160) AS excerpt
              FROM lib.entries e JOIN lib.libraries l ON l.id = e.library_id LEFT JOIN lib.folders f ON f.id = e.folder_id
             WHERE e.library_id = ANY(%(l)s) AND NOT e.is_deleted AND e.search_doc ILIKE %(like)s
             ORDER BY lower(e.title) LIMIT %(n)s""", q=q, w=q.split()[0], l=ids, like=f"%{q}%", n=limit) if r["id"] not in seen]
    folders = rows(conn, """SELECT f.guid::text AS id, f.name, l.guid::text AS library, f.library_id FROM lib.folders f
                              JOIN lib.libraries l ON l.id = f.library_id
                             WHERE f.library_id = ANY(%(l)s) AND NOT f.is_deleted AND f.name ILIKE %(like)s ORDER BY lower(f.name) LIMIT 20""",
                   l=ids, like=f"%{q}%")
    for r in found + folders:
        r["library_name"] = names.get(r.pop("library_id"), "")
        if "excerpt" in r:
            r["excerpt"] = re.sub(r"\s+", " ", r["excerpt"] or "").strip()
            r.pop("rank", None)
    return {"q": q, "results": found[:limit], "folders": folders}


# ---------------------------------------------------------------- the project's settings
def set_project(conn, person, lib: dict, rights: dict, data: dict) -> dict:
    need(rights, "admin")
    sets, msg = {}, []
    if "in_enterprise" in data:
        sets["in_enterprise"] = bool(data["in_enterprise"])
        msg.append("shown in the enterprise library" if sets["in_enterprise"] else "no longer in the enterprise library")
    if "external_link" in data:
        link = str(data.get("external_link") or "").strip()
        if link and not re.match(r"^https?://\S+$", link):
            raise Refused("The project's own library is a web address (https://...).")
        sets["external_link"] = link
        msg.append(f"its Library tab opens {link}" if link else "its library is EA Explorer's again")
    for k, v in sets.items():
        conn.execute(f"UPDATE lib.libraries SET {k} = %(v)s WHERE id = %(i)s", {"v": v, "i": lib["id"]})   # noqa: S608 - k is ours
    _change(conn, lib, person, "changed", "Library settings", before={k: lib[k] for k in sets}, after=sets)
    return {"message": f"{lib['project_name']}: {', '.join(msg)}." if msg else "Nothing to change."}


def published(conn) -> list[dict]:
    """The project libraries shown in the enterprise library."""
    return rows(conn, """SELECT guid::text AS id, project_guid::text AS project, project_name,
                                (SELECT count(*) FROM lib.entries e WHERE e.library_id = l.id AND NOT e.is_deleted) AS entries
                           FROM lib.libraries l WHERE scope = 'project' AND in_enterprise ORDER BY lower(project_name)""")


# ---------------------------------------------------------------- export and import (project backups), for the main API
def export_project(conn, project_guid: str) -> dict | None:
    lib = one(conn, "SELECT * FROM lib.libraries WHERE project_guid::text = %(g)s", g=project_guid)
    if not lib:
        return None
    fs = rows(conn, "SELECT id, guid::text AS guid, parent_id, name, sort_order FROM lib.folders WHERE library_id = %(l)s AND NOT is_deleted", l=lib["id"])
    es = rows(conn, """SELECT guid::text AS guid, folder_id, kind, title, description, tags, blocks, href, file_name, content_type,
                              encode(content, 'base64') AS content, sort_order, created_by, created_at
                         FROM lib.entries WHERE library_id = %(l)s AND NOT is_deleted""", l=lib["id"])
    for e in es:
        e["created_at"] = e["created_at"].isoformat()
    return {"format": "eax-library-project/1", "project_name": lib["project_name"], "in_enterprise": lib["in_enterprise"],
            "external_link": lib["external_link"], "folders": fs, "entries": es}


def import_project(conn, project_guid: str, project_name: str, data: dict, actor: str, keep_sharing: bool = False) -> dict:
    """A project's library from a backup, into the project (a restored project is a new project: a new library, not shown
    in the enterprise library until its admin says so; a project put back over itself keeps its sharing)."""
    import base64
    if (data or {}).get("format") != "eax-library-project/1":
        raise Refused("Not a project library export.")
    lib = one(conn, "SELECT * FROM lib.libraries WHERE project_guid::text = %(g)s", g=project_guid)
    if lib:
        conn.execute("DELETE FROM lib.libraries WHERE id = %(i)s", {"i": lib["id"]})
    lib = one(conn, """INSERT INTO lib.libraries (scope, project_guid, project_name, in_enterprise, external_link, created_by)
                       VALUES ('project', %(g)s::uuid, %(n)s, %(e)s, %(x)s, %(u)s) RETURNING *""",
              g=project_guid, n=project_name, e=bool(keep_sharing and data.get("in_enterprise")), x=data.get("external_link") or "", u=actor)
    new_f: dict[int, int] = {}
    pending = list(data.get("folders") or [])
    for _ in range(len(pending) + 1):                       # parents before children
        later = []
        for f in pending:
            if f["parent_id"] and f["parent_id"] not in new_f:
                later.append(f)
                continue
            r = one(conn, """INSERT INTO lib.folders (library_id, parent_id, name, sort_order, created_by) VALUES (%(l)s, %(p)s, %(n)s, %(s)s, %(u)s)
                             RETURNING id""", l=lib["id"], p=new_f.get(f["parent_id"]), n=f["name"], s=f.get("sort_order") or 0, u=actor)
            new_f[f["id"]] = r["id"]
        pending = later
        if not pending:
            break
    for e in data.get("entries") or []:
        content = base64.b64decode(e["content"]) if e.get("content") else None
        doc = {**e, "file_text": text_of(e.get("file_name") or "", content) if content else ""}
        conn.execute("""INSERT INTO lib.entries (library_id, folder_id, kind, title, description, tags, blocks, href, file_name, content_type,
                                                 content, file_size, search_doc, sort_order, created_by, changed_by, changed_at)
                        VALUES (%(l)s, %(f)s, %(k)s, %(t)s, %(d)s, %(tg)s, %(b)s, %(h)s, %(fn)s, %(ct)s, %(c)s, %(fs)s, %(s)s, %(so)s, %(cb)s, %(u)s, now())""",
                     {"l": lib["id"], "f": new_f.get(e.get("folder_id")), "k": e["kind"], "t": e["title"], "d": e.get("description") or "",
                      "tg": e.get("tags") or [], "b": json.dumps(e.get("blocks") or []), "h": e.get("href") or "", "fn": e.get("file_name") or "",
                      "ct": e.get("content_type") or "", "c": content, "fs": len(content or b""), "s": _search_doc(doc), "so": e.get("sort_order") or 0,
                      "cb": e.get("created_by") or actor, "u": actor})
    return {"library": str(lib["guid"]), "folders": len(new_f), "entries": len(data.get("entries") or [])}
