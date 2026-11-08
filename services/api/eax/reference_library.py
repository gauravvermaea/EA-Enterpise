"""The organisation's reference library (owner, 8 Nov 2026, D300): one library for everyone, beside each project's own
Reference area (D296).

- Entries are documents (files) or links, in a free folder tree; each has a title, a description, its source and tags.
- A file keeps every version: each version is its own document in the document store (Mayan), so any version can be
  downloaded. The text inside the current version is read out (eax/text_extract.py) and kept for search.
- Search: title, description, source, tags and the text inside the documents (PostgreSQL full text, English), with a
  short excerpt around what matched.
- Everyone signed in reads it. Only Super Admins change it.
- A project links to an entry from its Reference area (a link to #/reference-library/<id>: it always opens the
  library's current version).
"""

from __future__ import annotations

import mimetypes
import re
from typing import Any

from sqlalchemy import text

from . import permissions as perms
from . import projects as pj
from .metamodel_edit import EditError
from .text_extract import text_of

_rows, _one = pj._rows, pj._one

_TSV = "to_tsvector('english', e.title || ' ' || e.description || ' ' || e.source || ' ' || e.search_text)"


def may_write(user) -> bool:
    return perms.SUPER_ADMIN in (user.roles or ())


def _need_write(user) -> None:
    if not may_write(user):
        raise EditError("The reference library is changed by Super Admins; everyone reads it.", 403)


def clean_folder(path: str) -> str:
    parts = [re.sub(r"[^\w .()&,'-]+", "_", x).strip(" .")[:80] for x in str(path or "").replace("\\", "/").split("/")]
    return "/".join(x for x in parts if x)


def _tags(v: Any) -> list[str]:
    if isinstance(v, str):
        v = v.split(",")
    out = []
    for t in v or []:
        t = " ".join(str(t).split())[:40]
        if t and t.lower() not in {x.lower() for x in out}:
            out.append(t)
    return out[:30]


def _url(v: str) -> str:
    v = (v or "").strip()
    if not re.match(r"^https?://", v, re.I):
        raise EditError("A link's address starts with http:// or https://.")
    return v[:2000]


def _out(r: dict) -> dict:
    return {"id": str(r["guid"]), "folder": r["folder"], "kind": r["kind"], "title": r["title"], "description": r["description"],
            "source": r["source"], "tags": list(r["tags"] or []), "url": r["link_url"], "file_name": r["file_name"],
            "version": r["version"], "has_text": bool(r.get("has_text")), "created_by": r["created_by"], "created_at": r["created_at"],
            "modified_by": r["modified_by"] or r["created_by"], "modified_at": r["modified_at"] or r["created_at"],
            **({"excerpt": r["excerpt"]} if r.get("excerpt") else {})}


_COLS = """e.id, e.guid, e.folder, e.kind, e.title, e.description, e.source, e.tags, e.link_url, e.file_name, e.version,
           e.search_text <> '' AS has_text, e.created_by, e.created_at, e.modified_by, e.modified_at"""


def browse(conn, user, folder: str = "", q: str = "", tag: str = "", kind: str = "", deep: bool = False) -> dict:
    """The library: its folders (with how many entries each holds), its tags, and the entries of a folder, or every
    entry matching a search (q: words, searched in the documents' text too; tag; kind file or link)."""
    folder = clean_folder(folder)
    folders = _rows(conn, """SELECT f.path, f.description,
                                    (SELECT count(*) FROM proj.org_ref_entries e WHERE e.folder = f.path) AS entries
                               FROM proj.org_ref_folders f ORDER BY f.path""")
    tops = (_one(conn, "SELECT count(*) AS n FROM proj.org_ref_entries WHERE folder = ''") or {"n": 0})["n"]
    tags = _rows(conn, """SELECT t AS tag, count(*) AS n FROM proj.org_ref_entries, unnest(tags) AS t GROUP BY t ORDER BY lower(t)""")
    where, params = ["true"], {}
    q = (q or "").strip()[:200]
    if q:
        where.append(f"({_TSV} @@ websearch_to_tsquery('english', :q) OR e.title ILIKE :like OR array_to_string(e.tags, ' ') ILIKE :like)")
        params.update(q=q, like=f"%{q}%")
    if tag:
        where.append(":tag = ANY (e.tags)")
        params["tag"] = tag
    if kind in ("file", "link"):
        where.append("e.kind = :kind")
        params["kind"] = kind
    searching = bool(q or tag or kind)
    if folder or not searching:
        if deep or searching:
            where.append("(e.folder = :folder OR e.folder LIKE :under)" if folder else "true")
            params.update(folder=folder, under=f"{folder}/%")
        else:
            where.append("e.folder = :folder")
            params["folder"] = folder
    excerpt = (", ts_headline('english', e.search_text, websearch_to_tsquery('english', :q), "
               "'MaxFragments=2, MaxWords=18, MinWords=6, StartSel=«, StopSel=»') AS excerpt") if q else ""
    order = f"ts_rank({_TSV}, websearch_to_tsquery('english', :q)) DESC, lower(e.title)" if q else "e.folder, lower(e.title)"
    rows = _rows(conn, f"SELECT {_COLS}{excerpt} FROM proj.org_ref_entries e WHERE {' AND '.join(where)} ORDER BY {order} LIMIT 500",
                 **params)
    return {"folder": folder, "folders": [{**f, "entries": int(f["entries"])} for f in folders], "top_entries": int(tops),
            "tags": tags, "entries": [_out(r) for r in rows], "searching": searching, "may_write": may_write(user)}


def _entry(conn, eid: str) -> dict:
    r = _one(conn, f"SELECT {_COLS}, e.mayan_document_id FROM proj.org_ref_entries e WHERE e.guid = CAST(:g AS uuid)", g=eid)
    if not r:
        raise EditError("No such entry in the reference library.", 404)
    return r


def entry(conn, user, eid: str) -> dict:
    r = _entry(conn, eid)
    versions = _rows(conn, """SELECT version, file_name, size_bytes, note, by_user, at FROM proj.org_ref_versions
                                WHERE entry_id = :e ORDER BY version DESC""", e=r["id"])
    return {**_out(r), "versions": versions, "may_write": may_write(user)}


def _ensure_folder(conn, user, folder: str) -> None:
    parts = folder.split("/") if folder else []
    for i in range(len(parts)):
        conn.execute(text("INSERT INTO proj.org_ref_folders (path, added_by) VALUES (:p, :u) ON CONFLICT DO NOTHING"),
                     {"p": "/".join(parts[: i + 1]), "u": user.username})


def add_folder(conn, user, path: str, description: str = "") -> dict:
    _need_write(user)
    path = clean_folder(path)
    if not path:
        raise EditError("Give the folder a name.")
    if _one(conn, "SELECT 1 AS x FROM proj.org_ref_folders WHERE path = :p", p=path):
        raise EditError(f"{path} is there already.", 409)
    _ensure_folder(conn, user, path)
    conn.execute(text("UPDATE proj.org_ref_folders SET description = :d WHERE path = :p"), {"d": (description or "").strip()[:500], "p": path})
    return {"path": path, "message": f"Folder {path} made."}


def delete_folder(conn, user, path: str) -> dict:
    _need_write(user)
    path = clean_folder(path)
    n = (_one(conn, "SELECT count(*) AS n FROM proj.org_ref_entries WHERE folder = :p OR folder LIKE :u", p=path, u=f"{path}/%") or {"n": 0})["n"]
    if n:
        raise EditError(f"{path} holds {n} entr{'y' if n == 1 else 'ies'}: move or delete them first.", 409)
    conn.execute(text("DELETE FROM proj.org_ref_folders WHERE path = :p OR path LIKE :u"), {"p": path, "u": f"{path}/%"})
    return {"message": f"Folder {path} removed."}


def _meta(d: dict, base: dict | None = None) -> dict:
    v = {**(base or {}), **{k: d[k] for k in ("title", "description", "source", "tags", "folder") if k in d}}
    title = " ".join((v.get("title") or "").split())
    if not title:
        raise EditError("Give the entry a title.")
    return {"title": title[:300], "description": (v.get("description") or "").strip()[:4000], "source": (v.get("source") or "").strip()[:200],
            "tags": _tags(v.get("tags")), "folder": clean_folder(v.get("folder") or "")}


def add_link(conn, user, d: dict) -> dict:
    _need_write(user)
    m = _meta(d)
    url = _url(d.get("url"))
    _ensure_folder(conn, user, m["folder"])
    g = conn.execute(text("""INSERT INTO proj.org_ref_entries (folder, kind, title, description, source, tags, link_url, created_by)
                             VALUES (:folder, 'link', :title, :description, :source, CAST(:tags AS text[]), :url, :u) RETURNING guid::text"""),
                     {**m, "url": url, "u": user.username}).scalar()
    return {"id": g, "message": f"Link {m['title']} added."}


def add_file(conn, user, d: dict, file_name: str, content: bytes) -> dict:
    from . import mayan
    _need_write(user)
    if not file_name or not content:
        raise EditError("Choose a file to upload.")
    m = _meta({"title": file_name.rsplit(".", 1)[0].replace("_", " "), **{k: v for k, v in d.items() if v}})
    _ensure_folder(conn, user, m["folder"])
    doc = mayan.upload(file_name, content, mimetypes.guess_type(file_name)[0] or "application/octet-stream", label=f"Reference library: {m['title']}")
    r = _one(conn, """INSERT INTO proj.org_ref_entries (folder, kind, title, description, source, tags, file_name, mayan_document_id, version,
                                                        search_text, created_by)
                      VALUES (:folder, 'file', :title, :description, :source, CAST(:tags AS text[]), :f, :m, 1, :t, :u)
                      RETURNING id, guid::text AS guid""",
             **m, f=file_name[:300], m=doc["id"], t=text_of(file_name, content), u=user.username)
    conn.execute(text("""INSERT INTO proj.org_ref_versions (entry_id, version, file_name, size_bytes, mayan_document_id, note, by_user)
                         VALUES (:e, 1, :f, :s, :m, :n, :u)"""),
                 {"e": r["id"], "f": file_name[:300], "s": len(content), "m": doc["id"], "n": (d.get("note") or "").strip()[:500], "u": user.username})
    return {"id": r["guid"], "message": f"{m['title']} added to the reference library."}


def new_version(conn, user, eid: str, file_name: str, content: bytes, note: str = "") -> dict:
    from . import mayan
    _need_write(user)
    r = _entry(conn, eid)
    if r["kind"] != "file":
        raise EditError("A link has no file: change its address instead.")
    if not file_name or not content:
        raise EditError("Choose a file to upload.")
    v = int(r["version"]) + 1
    doc = mayan.upload(file_name, content, mimetypes.guess_type(file_name)[0] or "application/octet-stream",
                       label=f"Reference library: {r['title']} v{v}")
    conn.execute(text("""UPDATE proj.org_ref_entries SET file_name = :f, mayan_document_id = :m, version = :v, search_text = :t,
                                modified_by = :u, modified_at = now() WHERE id = :i"""),
                 {"f": file_name[:300], "m": doc["id"], "v": v, "t": text_of(file_name, content), "u": user.username, "i": r["id"]})
    conn.execute(text("""INSERT INTO proj.org_ref_versions (entry_id, version, file_name, size_bytes, mayan_document_id, note, by_user)
                         VALUES (:e, :v, :f, :s, :m, :n, :u)"""),
                 {"e": r["id"], "v": v, "f": file_name[:300], "s": len(content), "m": doc["id"], "n": (note or "").strip()[:500], "u": user.username})
    return {"id": eid, "version": v, "message": f"{r['title']}: version {v} kept (the earlier versions stay)."}


def update(conn, user, eid: str, d: dict) -> dict:
    _need_write(user)
    r = _entry(conn, eid)
    m = _meta(d, {k: r[k] for k in ("title", "description", "source", "tags", "folder")})
    url = _url(d["url"]) if r["kind"] == "link" and "url" in d else r["link_url"]
    _ensure_folder(conn, user, m["folder"])
    conn.execute(text("""UPDATE proj.org_ref_entries SET title = :title, description = :description, source = :source,
                                tags = CAST(:tags AS text[]), folder = :folder, link_url = :url, modified_by = :u, modified_at = now()
                          WHERE id = :i"""), {**m, "url": url, "u": user.username, "i": r["id"]})
    return {"id": eid, "message": f"{m['title']} saved."}


def delete(conn, user, eid: str) -> dict:
    from . import mayan
    _need_write(user)
    r = _entry(conn, eid)
    docs = [x["m"] for x in _rows(conn, "SELECT mayan_document_id AS m FROM proj.org_ref_versions WHERE entry_id = :e", e=r["id"]) if x["m"]]
    conn.execute(text("DELETE FROM proj.org_ref_entries WHERE id = :i"), {"i": r["id"]})
    for m in docs:                          # to the document store's trash (it can be got back from there)
        try:
            mayan.trash(m)
        except Exception:                   # noqa: BLE001 - the entry is gone either way
            pass
    return {"message": f"{r['title']} deleted from the reference library{' (its files are in the document store trash)' if docs else ''}."}


def file_of(conn, user, eid: str, version: int | None = None) -> tuple[bytes, str, str]:
    from . import mayan
    r = _entry(conn, eid)
    if r["kind"] != "file":
        raise EditError("A link has no file.")
    v = _one(conn, "SELECT mayan_document_id AS m, file_name FROM proj.org_ref_versions WHERE entry_id = :e AND version = :v",
             e=r["id"], v=int(version or r["version"]))
    if not v or not v["m"]:
        raise EditError("No such version.", 404)
    content, ctype, _name = mayan.download(v["m"])
    return content, ctype, v["file_name"]


def pick_list(conn, user, q: str = "") -> list[dict]:
    """Entries a project may link to from its Reference area (title, folder, kind), for the picker."""
    return [{"id": e["id"], "title": e["title"], "folder": e["folder"], "kind": e["kind"], "tags": e["tags"]}
            for e in browse(conn, user, "", q, deep=True)["entries"]]
