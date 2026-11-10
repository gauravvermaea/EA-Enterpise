"""The views service's API (phases 28 and 29, D405): /api/views/v1, behind the same proxy as the main API.

Every call carries the person's sign-in; the service asks the main API who they are, what they may do with the model's
views (read; draw, unless the model is frozen, archived or locked) and, on every save, whether the objects on the view
are the model's own entities (D354). What needs the model's data (the plugin's setup, resync, the relationships to draw,
heat maps, icons, generating a view's file) stays in the main API.
/internal is for the main API only (tags, copies, merges, packages, MCP and sample data), with the views key (EAX_VIEWS_KEY).

    GET  /health
    GET  /models/<m>/drawn-views                      the model's drawn views (with "the model changed since")
    POST /models/<m>/drawn-views                      {name, description?, xml?, source?, source_note?, copy_from?, copy_version?}
    GET  /models/<m>/drawn-views/<v>[?version=&xml=0] one view: its file, version, summary
    PUT  /models/<m>/drawn-views/<v>                  save {xml, base_version, note?, force?}: 409 {errors.conflict} when someone saved since
    PATCH /models/<m>/drawn-views/<v>                 rename or describe {name?, description?}
    DELETE /models/<m>/drawn-views/<v>                remove it (its versions are kept)
    GET  /models/<m>/drawn-views/<v>/versions         every version (and which a tag holds)
    GET  /models/<m>/own-views                        the model's own generated views (definitions, D406)
    POST /models/<m>/own-views                        {name, element_types, relationship_types?, heat_attribute?, purpose?, ..., copied_from?}
    GET/PUT/DELETE /models/<m>/own-views/<v>          one of them
"""

from __future__ import annotations

import hmac
import logging

from flask import Flask, g, jsonify, request

from . import __version__, main_api
from . import store as S
from .config import get_settings
from .db import connect
from .drawio import Refused

P = "/api/views/v1"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
    logging.basicConfig(level=logging.INFO)

    @app.errorhandler(Refused)
    def _refused(exc):
        return jsonify(message=str(exc), errors=exc.details or None), exc.status

    @app.errorhandler(main_api.Refused)
    def _main(exc):
        return jsonify(message=str(exc)), exc.status

    @app.errorhandler(413)
    def _too_big(_exc):
        return jsonify(message="A drawn view is at most 12 MB."), 413

    def person():
        if "person" not in g:
            g.person = main_api.whoami(dict(request.headers))
        return g.person

    def access(model: str, draw: bool = False) -> dict:
        """What the person may do with the model's views; refused when they may not read it, or draw when asked to."""
        a = main_api.model_access(person(), model)
        if draw and not a.get("may_draw"):
            raise Refused(a.get("read_only_reason") or "Not allowed: drawing this model's views needs a role on it that may "
                          "change its content.", 403)
        return a

    def checker(model: str):
        def check(parsed: dict) -> dict:
            return main_api.check(person(), model, parsed["entities"], [r["id"] for r in parsed["relationships"] if r.get("id")])
        return check

    def run(fn, write: bool = False, status: int = 200):
        with connect() as conn:
            out = fn(conn)
            conn.commit() if write else conn.rollback()
        return jsonify(out), status

    def body() -> dict:
        return request.get_json(silent=True) or {}

    # ---------------------------------------------------------------- health
    @app.get(f"{P}/health")
    def health():
        try:
            with connect() as conn:
                conn.execute("SELECT 1")
            return jsonify(status="up", version=__version__)
        except Exception as exc:  # noqa: BLE001
            return jsonify(status="down", error=str(exc)[:200]), 503

    # ---------------------------------------------------------------- drawn views
    @app.route(f"{P}/models/<model>/drawn-views", methods=["GET", "POST"])
    def views(model):
        if request.method == "GET":
            a = access(model)
            return run(lambda c: {**S.list_views(c, model, a.get("marker")), "may_draw": bool(a.get("may_draw")),
                                  "read_only_reason": a.get("read_only_reason")})
        a = access(model, draw=True)
        return run(lambda c: S.create(c, model, person().username, body(), a.get("marker"), checker(model)), write=True, status=201)

    @app.route(f"{P}/models/<model>/drawn-views/<view>", methods=["GET", "PUT", "PATCH", "DELETE"])
    def view(model, view):
        if request.method == "GET":
            a = access(model)
            return run(lambda c: {**S.get_view(c, model, view, request.args.get("version", type=int), request.args.get("xml", "1") != "0",
                                               a.get("marker")), "may_draw": bool(a.get("may_draw"))})
        a = access(model, draw=True)
        if request.method == "PUT":
            return run(lambda c: S.save(c, model, person().username, view, body(), a.get("marker"), checker(model)), write=True)
        if request.method == "PATCH":
            return run(lambda c: S.change(c, model, person().username, view, body()), write=True)
        return run(lambda c: S.delete(c, model, person().username, view), write=True)

    @app.get(f"{P}/models/<model>/drawn-views/<view>/versions")
    def versions(model, view):
        access(model)
        return run(lambda c: S.versions(c, model, view))

    # ---------------------------------------------------------------- the model's own generated views (D406)
    @app.route(f"{P}/models/<model>/own-views", methods=["GET", "POST"])
    def own(model):
        if request.method == "GET":
            a = access(model)
            return run(lambda c: {**S.own_views(c, model), "may_draw": bool(a.get("may_draw"))})
        access(model, draw=True)
        return run(lambda c: S.add_own(c, model, person().username, body()), write=True, status=201)

    @app.route(f"{P}/models/<model>/own-views/<view>", methods=["GET", "PUT", "DELETE"])
    def own_one(model, view):
        if request.method == "GET":
            access(model)
            return run(lambda c: S.own_view(c, model, view))
        access(model, draw=True)
        if request.method == "PUT":
            return run(lambda c: S.change_own(c, model, person().username, view, body()), write=True)
        return run(lambda c: S.delete_own(c, model, person().username, view), write=True)

    # ---------------------------------------------------------------- for the main API only
    def internal():
        key = get_settings().internal_key
        if not key or not hmac.compare_digest(key, request.headers.get("X-Views-Key", "")):
            raise Refused("Not allowed.", 403)

    def actor() -> str:
        return str(body().get("actor") or request.args.get("actor") or "system")[:120]

    @app.route(f"{P}/internal/models/<model>/drawn-views", methods=["GET", "POST"])
    def i_views(model):
        internal()
        if request.method == "GET":
            return run(lambda c: S.list_views(c, model, request.args.get("marker")))
        d = body()
        return run(lambda c: S.create(c, model, actor(), d, d.get("marker")), write=True, status=201)

    @app.route(f"{P}/internal/models/<model>/drawn-views/<view>", methods=["GET", "PUT"])
    def i_view(model, view):
        internal()
        if request.method == "GET":
            return run(lambda c: S.get_view(c, model, view, request.args.get("version", type=int), request.args.get("xml", "1") != "0",
                                             request.args.get("marker")))
        d = body()
        return run(lambda c: S.save(c, model, actor(), view, d, d.get("marker")), write=True)

    @app.post(f"{P}/internal/models/<model>/tags/<tag>")
    def i_tag(model, tag):
        internal()
        return run(lambda c: {"drawn_views": S.hold_for_tag(c, model, tag)}, write=True)

    @app.get(f"{P}/internal/models/<model>/tags/<tag>/drawn-views/<view>")
    def i_tag_view(model, tag, view):
        internal()
        return run(lambda c: S.tag_view(c, model, tag, view))

    @app.get(f"{P}/internal/models/<model>/export")
    def i_export(model):
        internal()
        return run(lambda c: S.export_model(c, model, request.args.get("all", "1") != "0"))

    @app.post(f"{P}/internal/models/<model>/import")
    def i_import(model):
        internal()
        d = body()
        return run(lambda c: S.import_model(c, model, d.get("views") or {}, actor(), d.get("ent_map"), d.get("rel_map"),
                                             bool(d.get("only_new")), d.get("source") or "package", bool(d.get("latest_only")),
                                             bool(d.get("replace"))), write=True)

    @app.post(f"{P}/internal/models/<model>/copy-to/<target>")
    def i_copy(model, target):
        internal()
        d = body()
        return run(lambda c: S.copy_model(c, model, target, actor(), d.get("ent_map") or {}, d.get("rel_map") or {},
                                           bool(d.get("only_new")), d.get("source") or "model-copy"), write=True)

    @app.delete(f"{P}/internal/models/<model>")
    def i_delete(model):
        internal()
        return run(lambda c: S.delete_model(c, model, actor()), write=True)

    return app
