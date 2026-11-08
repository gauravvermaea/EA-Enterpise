"""Links and the Reference area of a project's repository (owner, 8 Nov 2026, D296).

A **link** is an entry of the repository with no file: an external web address, or another project's document or
document class (shown as it is there now), or both. It is filed like a document (in a document class, or a folder),
tagged, marked a deliverable or an artifact, accepted or sent for sign-off; it has no check-out and no versions. TOGAF
lets the repository point outside: external reference models and standards, Board minutes kept elsewhere.

The **Reference** area is TOGAF's Reference Library (05_Reference_Library), opened up: folders of any shape, holding
documents and links, added by anyone on the project. When a project is made, the person may copy reference material
from the project it derives from, from its project template (links) and from library projects (projects a Super Admin
marks as libraries); the files are copied into the new repository once it is built (project_backup.refill_pending).
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import text

from . import projects as pj
from .metamodel_edit import EditError

_rows, _one = pj._rows, pj._one

REFERENCE = "05_Reference_Library"
LINK = "link"


def is_link(d: dict) -> bool:
    return bool(d.get("link_url") or d.get("link_project"))


def _url(v: str) -> str:
    v = (v or "").strip()
    if v and not re.match(r"^(https?://|#/)", v, re.I):
        raise EditError("A link's address starts with http:// or https://.")
    return v[:2000]


def _folder_of(conn, p: dict, d: dict) -> tuple[str, int | None, str | None]:
    """Where an entry goes: a document class of the project (its folder), or a folder of the Reference area."""
    if d.get("item"):
        it = _one(conn, "SELECT id, folder, kind FROM proj.items WHERE project_id = :p AND guid = CAST(:g AS uuid)", p=p["id"], g=d["item"])
        if not it:
            raise EditError("No such document class in this project.", 404)
        return it["folder"], it["id"], it["kind"]
    folder = clean_path(d.get("folder") or REFERENCE)
    if not folder.startswith(REFERENCE):
        raise EditError("A link goes into a document class or the Reference area.")
    return folder, None, None


def clean_path(path: str) -> str:
    parts = [re.sub(r"[^\w .()&,'-]+", "_", x).strip(" .")[:80] for x in str(path or "").replace("\\", "/").split("/")]
    parts = [x for x in parts if x]
    if not parts or parts[0] != REFERENCE:
        parts = [REFERENCE, *parts]
    return "/".join(parts)


def _target(conn, user, d: dict) -> dict:
    """A link to another project's document or document class: checked (the person must see that project)."""
    if not d.get("link_project"):
        return {"link_project": None, "link_document": None, "link_item": None}
    tp = pj.project_row(conn, d["link_project"])
    pj._need(conn, tp, user, "read")
    out = {"link_project": str(tp["guid"]), "link_document": None, "link_item": None}
    if d.get("link_document"):
        if not _one(conn, "SELECT 1 AS x FROM proj.documents WHERE project_id = :p AND guid = CAST(:g AS uuid)", p=tp["id"], g=d["link_document"]):
            raise EditError(f"No such document in {tp['name']}.", 404)
        out["link_document"] = d["link_document"]
    elif d.get("link_item"):
        if not _one(conn, "SELECT 1 AS x FROM proj.items WHERE project_id = :p AND guid = CAST(:g AS uuid)", p=tp["id"], g=d["link_item"]):
            raise EditError(f"No such document class in {tp['name']}.", 404)
        out["link_item"] = d["link_item"]
    return out


def add_link(conn, project: Any, user, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    title = (d.get("title") or "").strip()
    url = _url(d.get("url"))
    tgt = _target(conn, user, d)
    if not url and not tgt["link_project"]:
        raise EditError("Give the link's address, or choose another project's document.")
    if not title:
        raise EditError("Give the link a title.")
    folder, item_id, item_kind = _folder_of(conn, p, d)
    kind = d.get("kind") if d.get("kind") in ("Deliverable", "Artifact") else (item_kind or "Artifact")
    row = _one(conn, """INSERT INTO proj.documents (project_id, item_id, folder, file_name, origin, kind, link_url, link_project,
                                                    link_document, link_item, description, tags, created_by, modified_by)
                        VALUES (:p, :i, :f, :n, 'link', :k, :url, CAST(:lp AS uuid), CAST(:ld AS uuid), CAST(:li AS uuid), :de,
                                CAST(:tags AS text[]), :u, :u)
                        RETURNING id, guid::text AS guid""",
               p=p["id"], i=item_id, f=folder, n=title[:300], k=kind, url=url, lp=tgt["link_project"], ld=tgt["link_document"],
               li=tgt["link_item"], de=(d.get("description") or "").strip()[:2000],
               tags=[t.strip()[:40] for t in d.get("tags") or [] if t.strip()][:20], u=user.username)
    pj._event(conn, row["id"], user, "link added", None, url or "another project's document")
    return {"id": row["guid"], "message": f"Link {title} added to {folder.split('/')[-1]}."}


def update_link(conn, project: Any, user, doc: str, d: dict) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    r = pj._doc(conn, p, doc)
    if not is_link(r):
        raise EditError("Only a link is changed this way.")
    title = (d.get("title", r["file_name"]) or "").strip()
    if not title:
        raise EditError("Give the link a title.")
    url = _url(d.get("url", r["link_url"]))
    tgt = _target(conn, user, d) if "link_project" in d else {k: r[k] and str(r[k]) for k in ("link_project", "link_document", "link_item")}
    if not url and not tgt["link_project"]:
        raise EditError("Give the link's address, or choose another project's document.")
    conn.execute(text("""UPDATE proj.documents SET file_name = :n, link_url = :url, link_project = CAST(:lp AS uuid),
                                link_document = CAST(:ld AS uuid), link_item = CAST(:li AS uuid), description = :de,
                                modified_by = :u, modified_at = now() WHERE id = :i"""),
                 {"n": title[:300], "url": url, "lp": tgt["link_project"], "ld": tgt["link_document"], "li": tgt["link_item"],
                  "de": (d.get("description", r["description"]) or "").strip()[:2000], "u": user.username, "i": r["id"]})
    pj._event(conn, r["id"], user, "link changed", None, url)
    return {"id": doc, "message": f"Link {title} saved."}


def targets(conn, user, rows: list[dict]) -> None:
    """Each link to another project's document or class, as it is there now (name, state, version), when the person sees it."""
    want = {str(r["link_project"]) for r in rows if r.get("link_project")}
    if not want:
        return
    projects = {str(x["guid"]): x for x in _rows(conn, "SELECT id, guid, name FROM proj.projects WHERE guid::text = ANY (CAST(:g AS text[]))",
                                                     g=list(want))}
    seen = {}
    for g, tp in projects.items():
        try:
            pj._need(conn, tp, user, "read")
            seen[g] = tp
        except EditError:
            pass
    docs = {str(x["guid"]): x for x in _rows(conn, """SELECT d.guid, d.file_name, d.title, d.state, d.versions, d.user_version,
                                                              i.guid::text AS item, i.phase
                                                         FROM proj.documents d LEFT JOIN proj.items i ON i.id = d.item_id
                                                       WHERE d.guid::text = ANY (CAST(:g AS text[]))""",
                                             g=[str(r["link_document"]) for r in rows if r.get("link_document")])}
    items = {str(x["guid"]): x for x in _rows(conn, "SELECT guid, name, phase FROM proj.items WHERE guid::text = ANY (CAST(:g AS text[]))",
                                              g=[str(r["link_item"]) for r in rows if r.get("link_item")])}
    for r in rows:
        if not r.get("link_project"):
            continue
        g = str(r["link_project"])
        tp = seen.get(g)
        if not tp:
            r["link_target"] = {"visible": False}
            continue
        t = {"visible": True, "project": g, "project_name": tp["name"], "open": f"#/projects/{g}/home"}
        # opened on its phase's Documents, the document or class highlighted and scrolled to (owner, 8 Nov 2026)
        tab = lambda ph: "C" if ph in ("C-D", "C-A") else (ph or "X")  # noqa: E731
        if r.get("link_document") and str(r["link_document"]) in docs:
            x = docs[str(r["link_document"])]
            t.update(document=str(r["link_document"]), name=x["title"] or x["file_name"], state=x["state"], version=x["versions"],
                     user_version=x["user_version"], open=f"#/projects/{g}/phases?phase={tab(x['phase'])}&doc={r['link_document']}")
        elif r.get("link_item") and str(r["link_item"]) in items:
            x = items[str(r["link_item"])]
            t.update(item=str(r["link_item"]), name=x["name"], open=f"#/projects/{g}/phases?phase={tab(x['phase'])}&item={r['link_item']}")
        r["link_target"] = t


# ---------------------------------------------------------------- the Reference area
def reference(conn, project: Any, user) -> dict:
    p = pj.project_row(conn, project)
    roles = pj._need(conn, p, user, "read")
    folders = {r["path"] for r in _rows(conn, "SELECT path FROM proj.folders WHERE project_id = :p AND path LIKE :r",
                                        p=p["id"], r=f"{REFERENCE}%")}
    docs = [d for d in pj.documents(conn, p) if d["folder"].startswith(REFERENCE)]
    targets(conn, user, docs)
    folders |= {d["folder"] for d in docs}
    folders.add(REFERENCE)
    return {"root": REFERENCE, "folders": sorted(folders), "documents": docs,
            "may_edit": bool(roles & pj.CONTRIBUTORS) or "super-admin" in roles, "is_library": bool(p.get("is_library"))}


def add_folder(conn, project: Any, user, path: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    path = clean_path(path)
    if path == REFERENCE:
        raise EditError("Give the folder a name.")
    conn.execute(text("INSERT INTO proj.folders (project_id, path) VALUES (:p, :f) ON CONFLICT (project_id, path) DO NOTHING"),
                 {"p": p["id"], "f": path})
    return {"folder": path, "message": f"Folder {path.split('/', 1)[-1]} added to Reference."}


def delete_folder(conn, project: Any, user, path: str) -> dict:
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    path = clean_path(path)
    if path == REFERENCE:
        raise EditError("The Reference area itself stays.")
    if _one(conn, """SELECT 1 AS x FROM proj.documents WHERE project_id = :p AND (folder = :f OR folder LIKE :sub)
                       AND deleted_at IS NULL""", p=p["id"], f=path, sub=f"{path}/%"):
        raise EditError("The folder holds documents or links: move or delete them first.", 409)
    conn.execute(text("DELETE FROM proj.folders WHERE project_id = :p AND (path = :f OR path LIKE :sub) AND mayan_cabinet_id IS NULL"),
                 {"p": p["id"], "f": path, "sub": f"{path}/%"})
    return {"message": f"Folder {path.split('/', 1)[-1]} taken away."}


def upload(conn, project: Any, user, folder: str, file_name: str, content: bytes) -> dict:
    from . import project_work as pw
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    return pw._store(conn, p, user, clean_path(folder), file_name, content, origin="reference", kind="Artifact")


def set_library(conn, project: Any, user, on: bool) -> dict:
    from . import permissions as perms
    if perms.SUPER_ADMIN not in user.roles:
        raise EditError("Only a Super Admin marks a library project.", 403)
    p = pj.project_row(conn, project)
    conn.execute(text("UPDATE proj.projects SET is_library = :o WHERE id = :p"), {"o": bool(on), "p": p["id"]})
    return {"message": f"{p['name']} is {'now' if on else 'no longer'} a library project: its reference material is "
                       f"{'offered to' if on else 'not offered to'} new projects."}


# ---------------------------------------------------------------- reference material offered to a new project
def _entry(d: dict, source: str, project_name: str) -> dict:
    link = is_link(d)
    return {"source": source, "from": project_name, "doc": str(d["guid"]), "title": d["file_name"], "kind": "link" if link else "file",
            "url": d.get("link_url") or "", "folder": d["folder"].split("/", 1)[1] if "/" in d["folder"] else "",
            "description": d.get("description") or ""}


def sources(conn, user, parent: str | None = None, template: str | None = None) -> dict:
    """What a new project can copy into its Reference area: the parent's (when deriving), the template's links and every
    library project's (the person ticks what to copy)."""
    from . import project_templates as pt
    out = []
    projects = []
    if parent:
        pp = pj.project_row(conn, parent)
        pj._need(conn, pp, user, "read")
        projects.append(("parent", pp))
    for lp in _rows(conn, "SELECT * FROM proj.projects WHERE is_library ORDER BY name"):
        if not parent or str(lp["guid"]) != str(projects[0][1]["guid"]):
            projects.append(("library", lp))
    for src, pp in projects:
        for d in _rows(conn, """SELECT guid, file_name, folder, link_url, link_project, description, mayan_document_id FROM proj.documents
                                 WHERE project_id = :p AND folder LIKE :r AND archived_at IS NULL AND deleted_at IS NULL
                                 ORDER BY folder, file_name""", p=pp["id"], r=f"{REFERENCE}%"):
            if is_link(d) or d["mayan_document_id"]:
                out.append(_entry(d, src, pp["name"]))
    if template:
        try:
            t = pt.get(conn, template)
            for n, x in enumerate(t["spec"].get("reference") or []):
                out.append({"source": "template", "from": t["name"], "doc": f"template:{n}", "title": x.get("title") or x.get("url"),
                            "kind": "link", "url": x.get("url") or "", "folder": x.get("folder") or "", "description": x.get("description") or ""})
        except EditError:
            pass
    return {"reference": out}


def template_links(spec: dict) -> list[dict]:
    """A project template's reference links, checked (title, url, folder, description)."""
    out = []
    for x in (spec or {}).get("reference") or []:
        try:
            url = _url(x.get("url"))
        except EditError:
            continue
        if url:
            out.append({"title": (x.get("title") or url).strip()[:300], "url": url, "folder": (x.get("folder") or "").strip()[:200],
                        "description": (x.get("description") or "").strip()[:2000]})
    return out


def copy_into(conn, p: dict, user, picks: list, template: str | None = None) -> int:
    """The reference material ticked in the wizard, into the new project's Reference area: links at once; files once the
    repository is built (a pending copy, as a restore's files are put back)."""
    from . import project_backup as pb
    from . import project_templates as pt
    n, copies = 0, {}
    tlinks = []
    if template:
        try:
            tlinks = pt.get(conn, template)["spec"].get("reference") or []
        except EditError:
            tlinks = []
    for key in picks or []:
        key = str(key)
        if key.startswith("template:"):
            i = int(key.split(":", 1)[1])
            if i < len(tlinks):
                x = tlinks[i]
                _insert_link(conn, p, user, x["title"], x["url"], clean_path(f"{REFERENCE}/{x.get('folder') or ''}"), x.get("description") or "")
                n += 1
            continue
        d = _one(conn, "SELECT * FROM proj.documents WHERE guid = CAST(:g AS uuid) AND folder LIKE :r", g=key, r=f"{REFERENCE}%")
        if not d:
            continue
        src = _one(conn, "SELECT * FROM proj.projects WHERE id = :i", i=d["project_id"])
        if not (src.get("is_library") or str(src["id"]) == str(p.get("parent_id"))):
            pj._need(conn, src, user, "read")
        if is_link(d):
            _insert_link(conn, p, user, d["file_name"], d["link_url"], d["folder"], d["description"], d)
        else:
            g = _one(conn, """INSERT INTO proj.documents (project_id, folder, file_name, origin, kind, description, created_by, modified_by)
                              VALUES (:p, :f, :n, 'reference', 'Artifact', :de, :u, :u) RETURNING guid::text AS g""",
                     p=p["id"], f=d["folder"], n=d["file_name"], de=d["description"], u=user.username)["g"]
            copies[g] = d["mayan_document_id"]
        conn.execute(text("INSERT INTO proj.folders (project_id, path) VALUES (:p, :f) ON CONFLICT (project_id, path) DO NOTHING"),
                     {"p": p["id"], "f": d["folder"]})
        n += 1
    if copies:
        stash = pb.folder() / "_restoring"
        stash.mkdir(parents=True, exist_ok=True)
        f = stash / f"{p['guid']}.json"
        todo = json.loads(f.read_text()) if f.exists() else {"files": {}, "trash": [], "evidence": {}}
        todo.setdefault("copies", {}).update(copies)
        f.write_text(json.dumps(todo))
    return n


def _insert_link(conn, p: dict, user, title: str, url: str, folder: str, description: str, src: dict | None = None) -> None:
    conn.execute(text("""INSERT INTO proj.documents (project_id, folder, file_name, origin, kind, link_url, link_project, link_document,
                                                     link_item, description, created_by, modified_by)
                         VALUES (:p, :f, :n, 'link', 'Artifact', :url, :lp, :ld, :li, :de, :u, :u)"""),
                 {"p": p["id"], "f": folder, "n": title[:300], "url": url or "", "lp": (src or {}).get("link_project"),
                  "ld": (src or {}).get("link_document"), "li": (src or {}).get("link_item"), "de": description or "", "u": user.username})
    conn.execute(text("INSERT INTO proj.folders (project_id, path) VALUES (:p, :f) ON CONFLICT (project_id, path) DO NOTHING"),
                 {"p": p["id"], "f": folder})


def copy_files(conn_factory, project_id: int, copies: dict) -> tuple[str, dict]:
    """After the repository is built: each copied reference file, from its source document in Documents into this
    project's folder. Returns a message and what is still to copy."""
    from . import mayan
    from . import project_work as pw
    left, done, failed = {}, 0, []
    for doc_guid, src_mid in copies.items():
        try:
            with conn_factory() as conn:
                d = _one(conn, "SELECT * FROM proj.documents WHERE project_id = :p AND guid = CAST(:g AS uuid)", p=project_id, g=doc_guid)
                if not d or d["mayan_document_id"]:
                    continue
                p = _one(conn, "SELECT * FROM proj.projects WHERE id = :i", i=project_id)
                content, ctype, _name = mayan.download(int(src_mid))
                cid = pw._cabinet(conn, p, d["folder"])
                up = mayan.upload(d["file_name"], content, ctype or "application/octet-stream")
                mayan.add_to_cabinet(cid, up["id"])
                conn.execute(text("UPDATE proj.documents SET mayan_document_id = :m WHERE id = :i"), {"m": up["id"], "i": d["id"]})
            done += 1
        except Exception as exc:  # noqa: BLE001 - tried again on the next build
            left[doc_guid] = src_mid
            failed.append(str(exc)[:100])
    msg = f"{done} reference files copied." if done else ""
    if failed:
        msg += f" {len(failed)} not yet ({failed[0]}): tried again on the next build."
    return msg.strip(), left
