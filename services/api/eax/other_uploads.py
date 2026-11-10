"""A project's own uploads on the Other views and documents tab (owner, 10 Nov 2026, D461; amends D415 and D429).

Beside the ten sample templates (sample_documents.py), anyone on the project uploads files of any type (several at once,
50 MB each) with an optional title and description, and anyone on it downloads them. Only the person who uploaded a file,
the project's Project Admin or Lead Architect, or a Super Admin replaces it (the earlier file stays as an earlier version,
downloadable) or deletes it.

They are ordinary project documents, so nothing new is stored: a row in proj.documents (origin 'other', folder
"00_Project/Other documents", kind 'None') with its file in Documents (Mayan), whose versions keep the earlier files. So the
infrastructure, project and organisation backups and restores carry them as they carry every project document. They are
not deliverables: never signed off or accepted, not shown in the repository table (projects.documents leaves them out).
A delete is the repository's delete (D290): hidden, kept in Documents, restorable by a Super Admin from the database.
"""

from __future__ import annotations

import mimetypes
from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError

FOLDER = "00_Project/Other documents"
ORIGIN = "other"
MAX_BYTES = 50 * 1024 * 1024        # a file
MAX_FILES = 20                      # in one upload
READ_ONLY = ("finishing", "frozen", "merged", "closed")


def _clean(s: Any, n: int) -> str:
    return " ".join(str(s or "").split())[:n]


def _member(conn, p: dict, user, write: bool) -> set[str]:
    """Anyone on the project (any role, Stakeholder too) or a Super Admin; nothing changes while it is finished."""
    roles = pj.my_roles(conn, p, user)
    if not roles and not pj._super(user):
        raise EditError(f"Not allowed on {p['name']}: needs a role on this project.", 403)
    if write and p.get("status") in READ_ONLY:
        raise EditError(f"{p['name']} is {p['status']}: it is read only.", 409)
    return roles


def _may_change(d: dict, roles: set[str], user) -> bool:
    return (pj._super(user) or bool(roles & pj.ADMINS)
            or (d.get("created_by") or "").lower() == (getattr(user, "username", "") or "").lower())


def _upload_doc(conn, p: dict, doc: str) -> dict:
    d = pj._one(conn, """SELECT * FROM proj.documents WHERE project_id = :p AND guid = CAST(:d AS uuid) AND origin = :o
                          AND deleted_at IS NULL""", p=p["id"], d=doc, o=ORIGIN)
    if not d:
        raise EditError("No such upload in this project.", 404)
    return d


def _type_of(name: str) -> str:
    ext = name.rpartition(".")[2].lower() if "." in name else ""
    return ext or "file"


def _check_file(name: str, content: bytes) -> str:
    name = _clean(name.replace("/", "_").replace("\\", "_"), 250) or "file"
    if not content:
        raise EditError(f"{name} is empty: choose a file with something in it.")
    if len(content) > MAX_BYTES:
        raise EditError(f"{name} is larger than {MAX_BYTES // (1024 * 1024)} MB.", 413)
    return name


def listing(conn, project: Any, user) -> dict:
    p = pj.project_row(conn, project)
    roles = _member(conn, p, user, False)
    rows = pj._rows(conn, """SELECT guid::text AS id, file_name, title, description, file_size, versions, created_by, created_at,
                                    modified_by, modified_at, mayan_document_id IS NOT NULL AS stored
                               FROM proj.documents WHERE project_id = :p AND origin = :o AND deleted_at IS NULL
                              ORDER BY created_at DESC, id DESC""", p=p["id"], o=ORIGIN)
    for r in rows:
        r["type"] = _type_of(r["file_name"])
        r["may_change"] = _may_change(r, roles, user)
    return {"uploads": rows, "may_upload": p.get("status") not in READ_ONLY, "max_bytes": MAX_BYTES, "max_files": MAX_FILES}


def upload(conn, project: Any, user, files: list[tuple[str, bytes]], title: str = "", description: str = "") -> dict:
    """One or more files; a title and description given with several files go on each of them."""
    from . import mayan
    from . import project_work as pw
    p = pj.project_row(conn, project)
    _member(conn, p, user, True)
    files = [(n, c) for n, c in (files or []) if n or c]
    if not files:
        raise EditError("Choose one or more files to upload.")
    if len(files) > MAX_FILES:
        raise EditError(f"Upload at most {MAX_FILES} files at once.")
    checked = [(_check_file(n, c), c) for n, c in files]
    title, description = _clean(title, 300), str(description or "").strip()[:2000]
    cabinet = pw._cabinet(conn, p, FOLDER)
    made = []
    for name, content in checked:
        doc = mayan.upload(name, content, mimetypes.guess_type(name)[0] or "application/octet-stream")
        mayan.add_to_cabinet(cabinet, doc["id"])
        row = pj._one(conn, """INSERT INTO proj.documents (project_id, folder, mayan_document_id, file_name, title, description,
                                                            origin, kind, file_size, created_by, modified_by)
                               VALUES (:p, :f, :m, :n, :t, :de, :o, 'None', :s, :u, :u) RETURNING id, guid::text AS guid""",
                      p=p["id"], f=FOLDER, m=doc["id"], n=name, t=title, de=description, o=ORIGIN, s=len(content),
                      u=user.username)
        pj._event(conn, row["id"], user, "uploaded", 1, name)
        made.append({"id": row["guid"], "file_name": name})
    names = ", ".join(m["file_name"] for m in made[:3]) + (f" and {len(made) - 3} more" if len(made) > 3 else "")
    return {"uploads": made, "message": f"Uploaded {names}."}


def replace(conn, project: Any, user, doc: str, file_name: str, content: bytes, note: str = "") -> dict:
    """A new file for an upload: it becomes the current one and the earlier file stays as an earlier version."""
    from . import mayan
    p = pj.project_row(conn, project)
    roles = _member(conn, p, user, True)
    d = _upload_doc(conn, p, doc)
    if not _may_change(d, roles, user):
        raise EditError(f"Only {d['created_by']} (who uploaded it), the Project Admin, the Lead Architect or a Super Admin "
                        "can replace it.", 403)
    name = _check_file(file_name or d["file_name"], content)
    mayan.new_version(d["mayan_document_id"], name, content, _clean(f"{user.username}: {note}".strip(": "), 250),
                      mimetypes.guess_type(name)[0] or "application/octet-stream")
    conn.execute(text("""UPDATE proj.documents SET versions = versions + 1, file_name = :n, file_size = :s, modified_by = :u,
                                modified_at = now() WHERE id = :i"""),
                 {"n": name, "s": len(content), "u": user.username, "i": d["id"]})
    pj._event(conn, d["id"], user, "checked in", d["versions"] + 1, _clean(note, 500) or f"replaced by {name}")
    return {"id": doc, "message": f"{d['title'] or d['file_name']} replaced: version {d['versions'] + 1}; the earlier file is "
                                  "kept as an earlier version."}


def update(conn, project: Any, user, doc: str, title: Any = None, description: Any = None) -> dict:
    p = pj.project_row(conn, project)
    roles = _member(conn, p, user, True)
    d = _upload_doc(conn, p, doc)
    if not _may_change(d, roles, user):
        raise EditError(f"Only {d['created_by']} (who uploaded it), the Project Admin, the Lead Architect or a Super Admin "
                        "can change it.", 403)
    t = d["title"] if title is None else _clean(title, 300)
    de = d["description"] if description is None else str(description).strip()[:2000]
    conn.execute(text("UPDATE proj.documents SET title = :t, description = :de, modified_by = :u, modified_at = now() WHERE id = :i"),
                 {"t": t, "de": de, "u": user.username, "i": d["id"]})
    pj._event(conn, d["id"], user, "details changed", d["versions"], t)
    return {"id": doc, "message": "Saved."}


def delete(conn, project: Any, user, doc: str) -> dict:
    p = pj.project_row(conn, project)
    roles = _member(conn, p, user, True)
    d = _upload_doc(conn, p, doc)
    if not _may_change(d, roles, user):
        raise EditError(f"Only {d['created_by']} (who uploaded it), the Project Admin, the Lead Architect or a Super Admin "
                        "can delete it.", 403)
    conn.execute(text("UPDATE proj.documents SET deleted_at = now(), deleted_by = :u WHERE id = :i"), {"u": user.username, "i": d["id"]})
    pj._event(conn, d["id"], user, "deleted", d["versions"])
    return {"id": doc, "message": f"{d['title'] or d['file_name']} deleted."}


def _need_upload(conn, project: Any, user, doc: str) -> dict:
    p = pj.project_row(conn, project)
    _member(conn, p, user, False)
    return _upload_doc(conn, p, doc)


def versions(conn, project: Any, user, doc: str) -> list[dict]:
    """The upload's files, newest first: number, who, when and the note."""
    d = _need_upload(conn, project, user, doc)
    rows = pj._rows(conn, """SELECT DISTINCT ON (version) version, at, by_user,
                                    CASE WHEN action = 'uploaded' THEN 'First upload: ' || note ELSE note END AS note
                               FROM proj.document_events
                              WHERE document_id = :d AND action IN ('uploaded', 'checked in') AND version IS NOT NULL
                              ORDER BY version, at DESC""", d=d["id"])
    return sorted([r for r in rows if 1 <= r["version"] <= d["versions"]], key=lambda r: -r["version"])


def download(conn, project: Any, user, doc: str, version: int | None = None) -> tuple[bytes, str, str]:
    from . import mayan
    d = _need_upload(conn, project, user, doc)
    if version is None or int(version) == d["versions"]:
        content, ctype, _n = mayan.download(d["mayan_document_id"])
        return content, ctype, d["file_name"]
    if not 1 <= int(version) <= d["versions"]:
        raise EditError(f"{d['file_name']} has versions 1 to {d['versions']}.", 404)
    content, ctype, name = mayan.download_version(d["mayan_document_id"], int(version))
    base, dot, ext = (name or d["file_name"]).rpartition(".")
    return content, ctype, f"{base} (v{version}).{ext}" if dot else f"{name} (v{version})"
