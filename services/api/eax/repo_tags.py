"""Tags on a project's whole repository (owner, 8 Nov 2026, D312).

A tag records the version of every document at that moment (and whether it was archived). With a tag one can:
- download every document as it was at the tag (one zip, a folder per document class);
- bring the repository back to the tag: a tag "before application of tag <name>" is made first (so nothing is lost),
  then each document that changed gets a new version that is a copy of its version at the tag, documents archived since
  come back, and documents added after the tag are archived.
Links have no versions: they are not in a tag. A document with no file yet is in it at version 0 (nothing to download
or bring back; it is not archived by a revert when its file came later).
Also here: the documents of a class, or of the whole repository, as they are now, in one zip.
"""

from __future__ import annotations

import io
import mimetypes
import re
import zipfile
from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError

_rows, _one = pj._rows, pj._one


def _clean(name: str) -> str:
    return " ".join((name or "").split())[:120]


def listing(conn, project: Any, user) -> dict:
    p = pj.project_row(conn, project)
    roles = pj._need(conn, p, user, "read")
    tags = _rows(conn, """SELECT t.guid::text AS id, t.name, t.note, t.auto, t.created_by, t.created_at,
                                 (SELECT count(*) FROM proj.repo_tag_docs x WHERE x.tag_id = t.id AND NOT x.archived AND x.version > 0) AS documents
                            FROM proj.repo_tags t WHERE t.project_id = :p ORDER BY t.created_at DESC, t.id DESC""", p=p["id"])
    live = p.get("status") not in ("finishing", "frozen", "merged", "closed")
    return {"tags": tags, "may_tag": live and (bool(roles & pj.CONTRIBUTORS) or "super-admin" in roles),
            "may_revert": live and (bool(roles & pj.ADMINS) or "super-admin" in roles)}


def _snapshot(conn, p: dict, name: str, note: str, by: str, auto: bool = False) -> dict:
    if _one(conn, "SELECT 1 AS x FROM proj.repo_tags WHERE project_id = :p AND lower(name) = lower(:n)", p=p["id"], n=name):
        raise EditError(f"The repository already has a tag named {name}.", 409)
    t = _one(conn, """INSERT INTO proj.repo_tags (project_id, name, note, auto, created_by) VALUES (:p, :n, :no, :a, :u)
                      RETURNING id, guid::text AS guid""", p=p["id"], n=name, no=note, a=auto, u=by)
    n = conn.execute(text("""INSERT INTO proj.repo_tag_docs (tag_id, document_id, version, user_version, file_name, title, archived)
                             SELECT :t, d.id, d.versions, coalesce(d.user_version, ''), d.file_name, d.title, d.archived_at IS NOT NULL
                               FROM proj.documents d
                              WHERE d.project_id = :p AND d.deleted_at IS NULL
                                AND d.link_url = '' AND d.link_project IS NULL"""), {"t": t["id"], "p": p["id"]}).rowcount
    return {"id": t["guid"], "documents": n}


def add(conn, project: Any, user, name: str, note: str = "") -> dict:
    """Tags the whole repository now: anyone who contributes."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    name = _clean(name)
    if not name:
        raise EditError("Name the tag, for example Phase B sign-off.")
    out = _snapshot(conn, p, name, (note or "").strip()[:2000], user.username)
    return {**out, "message": f"Tagged the repository {name}: {out['documents']} documents at their current versions."}


def delete(conn, project: Any, user, tag: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "admin")
    t = _tag(conn, p, tag)
    conn.execute(text("DELETE FROM proj.repo_tags WHERE id = :t"), {"t": t["id"]})
    return {"message": f"The tag {t['name']} is removed (the documents are not changed)."}


def _tag(conn, p: dict, tag: str) -> dict:
    t = _one(conn, "SELECT * FROM proj.repo_tags WHERE project_id = :p AND guid = CAST(:g AS uuid)", p=p["id"], g=tag)
    if not t:
        raise EditError("No such tag on this project's repository.", 404)
    return t


def detail(conn, project: Any, user, tag: str) -> dict:
    """The documents at the tag, each with its version then and now."""
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    t = _tag(conn, p, tag)
    docs = _rows(conn, """SELECT d.guid::text AS id, coalesce(nullif(x.title, ''), x.file_name) AS name, x.version, x.user_version,
                                 x.archived, d.versions AS now_version, d.user_version AS now_user_version, i.name AS class
                            FROM proj.repo_tag_docs x JOIN proj.documents d ON d.id = x.document_id
                            LEFT JOIN proj.items i ON i.id = d.item_id
                           WHERE x.tag_id = :t AND d.deleted_at IS NULL AND x.version > 0 ORDER BY i.name, name""", t=t["id"])
    added = _rows(conn, """SELECT d.guid::text AS id, coalesce(nullif(d.title, ''), d.file_name) AS name FROM proj.documents d
                            WHERE d.project_id = :p AND d.deleted_at IS NULL AND d.archived_at IS NULL AND d.mayan_document_id IS NOT NULL
                              AND d.link_url = '' AND d.link_project IS NULL
                              AND NOT EXISTS (SELECT 1 FROM proj.repo_tag_docs x WHERE x.tag_id = :t AND x.document_id = d.id)""",
                  p=p["id"], t=t["id"])
    return {"tag": {"id": tag, "name": t["name"], "note": t["note"], "auto": t["auto"], "created_by": t["created_by"],
                    "created_at": t["created_at"]}, "documents": docs, "added_since": added}


# ---------------------------------------------------------------- zips
def _zip_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", s).strip() or "document"


def _zip(rows: list[dict], read) -> bytes:
    """rows: {folder, name, mayan, version}; read(mayan, version) -> bytes. Names repeated in a folder get (2), (3)..."""
    buf = io.BytesIO()
    used: set[str] = set()
    missing = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in rows:
            path = f"{_zip_name(r['folder'])}/{_zip_name(r['name'])}"
            base, dot, ext = path.rpartition(".")
            k = 2
            while path.lower() in used:
                path = f"{base} ({k}).{ext}" if dot else f"{r['folder']}/{r['name']} ({k})"
                k += 1
            used.add(path.lower())
            try:
                z.writestr(path, read(r["mayan"], r["version"]))
            except Exception as exc:  # noqa: BLE001 - said in the zip, the others still come
                missing.append(f"{path}: {exc}")
        if missing:
            z.writestr("Not included.txt", "These could not be read from Documents:\n" + "\n".join(missing) + "\n")
    return buf.getvalue()


def _class_folder(r: dict) -> str:
    return f"{r['phase'] or 'X'} - {r['class']}" if r.get("class") else (r.get("folder") or "Other").split("/")[-1]


def zip_documents(conn, project: Any, user, tag: str = "", item: str = "") -> tuple[bytes, str]:
    """Every document at a tag (its version then), or as it is now (the whole repository, or one class): one zip, a
    folder per document class."""
    from . import mayan
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    if tag:
        t = _tag(conn, p, tag)
        rows = _rows(conn, """SELECT d.mayan_document_id AS mayan, x.version, x.file_name AS name, i.name AS class, i.phase, d.folder
                                FROM proj.repo_tag_docs x JOIN proj.documents d ON d.id = x.document_id
                                LEFT JOIN proj.items i ON i.id = d.item_id
                               WHERE x.tag_id = :t AND NOT x.archived AND x.version > 0 ORDER BY i.phase, i.name, x.file_name""", t=t["id"])
        label = f"{p['name']} at {t['name']}"
    else:
        it = None
        if item:
            it = _one(conn, "SELECT id, name FROM proj.items WHERE project_id = :p AND guid = CAST(:i AS uuid)", p=p["id"], i=item)
            if not it:
                raise EditError("No such document class in this project.", 404)
        rows = _rows(conn, f"""SELECT d.mayan_document_id AS mayan, d.versions AS version, d.file_name AS name, i.name AS class, i.phase, d.folder
                                 FROM proj.documents d LEFT JOIN proj.items i ON i.id = d.item_id
                                WHERE d.project_id = :p AND d.deleted_at IS NULL AND d.archived_at IS NULL
                                  AND d.mayan_document_id IS NOT NULL AND d.versions > 0 AND d.link_url = '' AND d.link_project IS NULL
                                  {"AND d.item_id = :i" if it else ""} ORDER BY i.phase, i.name, d.file_name""", p=p["id"], i=(it or {}).get("id"))
        label = f"{p['name']} - {it['name']}" if it else f"{p['name']} documents"
    if not rows:
        raise EditError("There is no document with a file to download here.", 404)
    for r in rows:
        r["folder"] = _class_folder(r)
    return _zip(rows, lambda m, v: mayan.download_version(m, v)[0]), f"{_zip_name(label)}.zip"


# ---------------------------------------------------------------- back to a tag
def revert(conn, project: Any, user, tag: str) -> dict:
    """The repository back to a tag (a Project Admin or Lead Architect). First a tag "before application of tag <name>"
    keeps how it is now; then every document that changed gets a new version, a copy of its version at the tag; documents
    archived since come back; documents added after the tag are archived. Refused while a document is checked out."""
    from . import mayan
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "admin")
    t = _tag(conn, p, tag)
    out = _rows(conn, """SELECT coalesce(nullif(title, ''), file_name) AS name, checked_out_by FROM proj.documents
                          WHERE project_id = :p AND checked_out_by IS NOT NULL AND deleted_at IS NULL""", p=p["id"])
    if out:
        raise EditError("Checked out now, so the repository cannot go back yet: " +
                        ", ".join(f"{r['name']} ({r['checked_out_by']})" for r in out[:10]), 409)
    before = f"before application of tag {t['name']}"
    n = 2
    while _one(conn, "SELECT 1 AS x FROM proj.repo_tags WHERE project_id = :p AND lower(name) = lower(:n)", p=p["id"], n=before):
        before = f"before application of tag {t['name']} ({n})"
        n += 1
    _snapshot(conn, p, before, f"Made by {user.username} before bringing the repository back to {t['name']}.", user.username, auto=True)
    rows = _rows(conn, """SELECT d.*, x.version AS t_version, x.user_version AS t_user_version, x.file_name AS t_file_name,
                                 x.archived AS t_archived
                            FROM proj.repo_tag_docs x JOIN proj.documents d ON d.id = x.document_id WHERE x.tag_id = :t""", t=t["id"])
    changed = back = gone = 0
    # every file wanted is read first (nothing written yet: a failure here changes nothing); then each document gets its
    # copy. A copy Documents took on an earlier try that then failed is not added again (it has one file more than we
    # count) (review, 8 Nov 2026)
    files: dict[int, tuple] = {}
    for d in rows:
        if not d["deleted_at"] and d["t_version"] > 0 and d["mayan_document_id"] and d["versions"] != d["t_version"]:
            if d["t_version"] > d["versions"]:
                raise EditError(f"{d['t_file_name'] or d['file_name']}: the tag has version {d['t_version']}, the document only {d['versions']}.", 409)
            files[d["id"]] = mayan.download_version(d["mayan_document_id"], d["t_version"])
    for d in rows:
        if d["deleted_at"]:
            continue
        if d["id"] in files:
            content, ctype, _n = files[d["id"]]
            note = f"{user.username}: back to tag {t['name']} (version {d['t_version']})"
            try:
                held = len(mayan.files(d["mayan_document_id"]))
            except Exception:  # noqa: BLE001
                held = None
            if held is None or held <= d["versions"]:
                mayan.new_version(d["mayan_document_id"], d["t_file_name"] or d["file_name"], content, note,
                                  mimetypes.guess_type(d["t_file_name"] or d["file_name"])[0] or ctype)
            conn.execute(text("""UPDATE proj.documents SET versions = versions + 1, file_name = :n, user_version = :uv,
                                        modified_by = :u, modified_at = now(),
                                        state = CASE WHEN state IN ('Approved', 'Accepted', 'Rejected') THEN 'Draft' ELSE state END
                                  WHERE id = :i"""),
                         {"n": d["t_file_name"] or d["file_name"], "uv": d["t_user_version"], "u": user.username, "i": d["id"]})
            pj._event(conn, d["id"], user, "back to a tag", d["versions"] + 1,
                      f"copy of version {d['t_version']}, as at the tag {t['name']}", d["t_user_version"])
            changed += 1
        if d["archived_at"] and not d["t_archived"]:
            conn.execute(text("UPDATE proj.documents SET archived_at = NULL, archived_by = NULL WHERE id = :i"), {"i": d["id"]})
            pj._event(conn, d["id"], user, "restored", d["versions"], f"back to the tag {t['name']}")
            back += 1
        elif not d["archived_at"] and d["t_archived"]:
            conn.execute(text("UPDATE proj.documents SET archived_at = now(), archived_by = :u WHERE id = :i"), {"u": user.username, "i": d["id"]})
            pj._event(conn, d["id"], user, "archived", d["versions"], f"archived at the tag {t['name']}")
            gone += 1
    newer = _rows(conn, """SELECT d.id, d.versions FROM proj.documents d
                            WHERE d.project_id = :p AND d.deleted_at IS NULL AND d.archived_at IS NULL AND d.mayan_document_id IS NOT NULL
                              AND d.link_url = '' AND d.link_project IS NULL
                              AND NOT EXISTS (SELECT 1 FROM proj.repo_tag_docs x WHERE x.tag_id = :t AND x.document_id = d.id)""",
                  p=p["id"], t=t["id"])
    for d in newer:
        conn.execute(text("UPDATE proj.documents SET archived_at = now(), archived_by = :u WHERE id = :i"), {"u": user.username, "i": d["id"]})
        pj._event(conn, d["id"], user, "archived", d["versions"], f"added after the tag {t['name']}")
    return {"message": f"The repository is back at {t['name']}: {changed} document{'' if changed == 1 else 's'} got a new version copied from the tag, "
                       f"{back} came back from the archive, {gone + len(newer)} archived ({len(newer)} added after the tag). "
                       f"How it was is kept in the tag \"{before}\".", "before": before}
