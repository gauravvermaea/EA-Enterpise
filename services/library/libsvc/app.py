"""The library service's API (phase 15.2, D346): /api/library/v1, behind the same proxy as the main API.

Every call carries the person's sign-in; the service asks the main API who they are and what they may do in a project.
/internal is for the main API only (project backups and sample data), with the library key (EAX_LIBRARY_KEY).

    GET  /health
    GET  /libraries/org                            the enterprise library: folders, what you may do, project libraries shown in it
    GET  /libraries/project/<project>              a project's library (made the first time)
    PUT  /libraries/project/<project>              {in_enterprise, external_link} (the project's admins)
    GET  /libraries/<lib>                          one library (folders, what you may do): a project library shown in the enterprise one
    GET  /libraries/<lib>/entries?folder=          a folder's entries (none: the top)
    POST /libraries/<lib>/entries                  a page {kind: page, title, blocks}, a link {kind: link, title, href} or a file (multipart)
    GET/PUT/DELETE /libraries/<lib>/entries/<e>    one entry; change it (title, description, tags, blocks, href, folder); remove it
    POST/DELETE /libraries/<lib>/entries/<e>/hold  hold a page while editing it; let it go
    GET  /libraries/<lib>/entries/<e>/file         the file
    POST /libraries/<lib>/folders                  {name, parent};  PUT/DELETE /libraries/<lib>/folders/<f>
    GET  /libraries/<lib>/history?entry=           recent changes (an entry's, or the library's)
    GET  /libraries/<lib>/changes/<id>             a change with its before and after
    POST /libraries/<lib>/changes/<id>/undo        undo it (enterprise: Library Admins and Super Admins; project: its admins)
    GET  /search?q=&library=<lib>|org              search a library (org: the enterprise library and the project libraries in it)
"""

from __future__ import annotations

import hmac
import logging
from urllib.parse import quote

from flask import Flask, Response, g, jsonify, request

from . import __version__, main_api
from . import library as L
from .config import get_settings
from .db import connect

P = "/api/library/v1"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = (get_settings().max_file_mb + 2) * 1024 * 1024
    logging.basicConfig(level=logging.INFO)

    @app.errorhandler(L.Refused)
    def _refused(exc):
        return jsonify(message=str(exc)), exc.status

    @app.errorhandler(main_api.Refused)
    def _main(exc):
        return jsonify(message=str(exc)), exc.status

    @app.errorhandler(413)
    def _too_big(_exc):
        return jsonify(message=f"A file in the library is at most {get_settings().max_file_mb} MB."), 413

    def person():
        if "person" not in g:
            g.person = main_api.whoami(dict(request.headers))
        return g.person

    def run(fn, write: bool = False):
        with connect() as conn:
            out = fn(conn)
            conn.commit() if write else conn.rollback()
        return jsonify(out)

    def lib_for(conn, lib_id: str, what: str = "read"):
        lib, rights = L.library(conn, person(), lib_id)
        L.need(rights, what)
        return lib, rights

    def body() -> tuple[dict, str, bytes]:
        if request.files.get("file"):
            f = request.files["file"]
            return dict(request.form), f.filename or "file", f.read()
        return request.get_json(silent=True) or dict(request.form), "", b""

    # ---------------------------------------------------------------- health
    @app.get(f"{P}/health")
    def health():
        try:
            with connect() as conn:
                conn.execute("SELECT 1")
            return jsonify(status="up", version=__version__)
        except Exception as exc:  # noqa: BLE001
            return jsonify(status="down", error=str(exc)[:200]), 503

    # ---------------------------------------------------------------- libraries
    def _summary(conn, lib, rights, extra=None):
        return {"id": str(lib["guid"]), "scope": lib["scope"], "project": str(lib["project_guid"]) if lib["project_guid"] else None,
                "name": "Enterprise library" if lib["scope"] == "org" else lib["project_name"], "in_enterprise": lib["in_enterprise"],
                "external_link": lib["external_link"], "folders": L.tree(conn, lib),
                "may": {k: rights.get(k, False) for k in ("read", "write", "admin")}, **(extra or {})}

    @app.get(f"{P}/libraries/org")
    def org():
        def go(conn):
            lib = L.org_library(conn)
            rights = L.may(conn, person(), lib)
            return _summary(conn, lib, rights, {"published": L.published(conn), "settings": main_api.library_settings(person())})
        return run(go)

    @app.route(f"{P}/libraries/project/<project>", methods=["GET", "PUT"])
    def project_lib(project):
        def go(conn):
            lib, _p = L.project_library(conn, person(), project)
            rights = L.may(conn, person(), lib)
            out = L.set_project(conn, person(), lib, rights, request.get_json(silent=True) or {}) if request.method == "PUT" else None
            if out:
                return out
            return _summary(conn, lib, rights)
        return run(go, write=True)

    @app.get(f"{P}/libraries/<lib_id>")
    def one_library(lib_id):
        def go(conn):
            lib, rights = lib_for(conn, lib_id)
            return _summary(conn, lib, rights)
        return run(go)

    # ---------------------------------------------------------------- entries
    @app.route(f"{P}/libraries/<lib_id>/entries", methods=["GET", "POST"])
    def entries(lib_id):
        if request.method == "GET":
            return run(lambda c: L.entries(c, lib_for(c, lib_id)[0], request.args.get("folder") or None))
        data, name, content = body()
        return run(lambda c: L.add_entry(c, person(), lib_for(c, lib_id, "write")[0], data, name, content), write=True)

    @app.route(f"{P}/libraries/<lib_id>/entries/<eid>", methods=["GET", "PUT", "DELETE"])
    def entry(lib_id, eid):
        if request.method == "GET":
            return run(lambda c: L.get_entry(c, lib_for(c, lib_id)[0], eid))
        if request.method == "PUT":
            return run(lambda c: L.change_entry(c, person(), lib_for(c, lib_id, "write")[0], eid, request.get_json(silent=True) or {}), write=True)
        return run(lambda c: L.remove_entry(c, person(), lib_for(c, lib_id, "write")[0], eid), write=True)

    @app.route(f"{P}/libraries/<lib_id>/entries/<eid>/hold", methods=["POST", "DELETE"])
    def hold(lib_id, eid):
        return run(lambda c: L.hold(c, person(), lib_for(c, lib_id, "write")[0], eid, request.method == "POST"), write=True)

    @app.get(f"{P}/libraries/<lib_id>/entries/<eid>/file")
    def file(lib_id, eid):
        with connect() as conn:
            data, name, ctype = L.file_of(conn, lib_for(conn, lib_id)[0], eid)
        return Response(data, mimetype=ctype, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})

    # ---------------------------------------------------------------- folders
    @app.post(f"{P}/libraries/<lib_id>/folders")
    def add_folder(lib_id):
        return run(lambda c: L.add_folder(c, person(), lib_for(c, lib_id, "write")[0], request.get_json(silent=True) or {}), write=True)

    @app.route(f"{P}/libraries/<lib_id>/folders/<fid>", methods=["PUT", "DELETE"])
    def folder(lib_id, fid):
        if request.method == "PUT":
            return run(lambda c: L.change_folder(c, person(), lib_for(c, lib_id, "write")[0], fid, request.get_json(silent=True) or {}), write=True)
        return run(lambda c: L.remove_folder(c, person(), lib_for(c, lib_id, "write")[0], fid), write=True)

    # ---------------------------------------------------------------- history and undo
    @app.get(f"{P}/libraries/<lib_id>/history")
    def history(lib_id):
        return run(lambda c: {"changes": L.history(c, lib_for(c, lib_id)[0], request.args.get("entry") or None)})

    @app.get(f"{P}/libraries/<lib_id>/changes/<int:cid>")
    def change(lib_id, cid):
        return run(lambda c: L.change_detail(c, lib_for(c, lib_id)[0], cid))

    @app.post(f"{P}/libraries/<lib_id>/changes/<int:cid>/undo")
    def undo(lib_id, cid):
        return run(lambda c: L.undo(c, person(), lib_for(c, lib_id, "admin")[0], cid), write=True)

    # ---------------------------------------------------------------- search
    @app.get(f"{P}/search")
    def search():
        def go(conn):
            which = request.args.get("library") or "org"
            if which == "org":
                libs = [L.org_library(conn)] + [L.one(conn, "SELECT * FROM lib.libraries WHERE guid::text = %(g)s", g=p["id"]) for p in L.published(conn)]
            else:
                libs = [lib_for(conn, which)[0]]
            return L.search(conn, [x for x in libs if x], request.args.get("q") or "")
        return run(go)

    # ---------------------------------------------------------------- for the main API only
    def internal():
        key = get_settings().internal_key
        given = request.headers.get("X-Library-Key", "")
        if not key or not hmac.compare_digest(key, given):
            raise L.Refused("Not allowed.", 403)

    @app.get(f"{P}/internal/projects/<project>/export")
    def export(project):
        internal()
        with connect() as conn:
            return jsonify(L.export_project(conn, project) or {})

    @app.post(f"{P}/internal/projects/<project>/import")
    def import_(project):
        internal()
        d = request.get_json(silent=True) or {}
        return run(lambda c: L.import_project(c, project, d.get("project_name") or "", d.get("library") or {}, d.get("actor") or "system",
                                                 bool(d.get("keep_sharing"))), write=True)

    @app.get(f"{P}/internal/org/export")
    def export_org():
        internal()
        with connect() as conn:
            return jsonify(L.export_org(conn) or {})

    @app.post(f"{P}/internal/org/import")
    def import_org():
        internal()
        d = request.get_json(silent=True) or {}
        return run(lambda c: L.import_org(c, d.get("library") or {}, d.get("actor") or "system"), write=True)

    @app.post(f"{P}/internal/seed")
    def seed():
        internal()
        from .seed import sample
        return run(lambda c: sample(c, request.get_json(silent=True) or {}), write=True)

    return app
