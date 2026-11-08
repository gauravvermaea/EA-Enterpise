"""Common analysis (phase 13.0.5, D286): what two or more models have in common, stored in a model you choose.

POST   /commons/preview                     {sides}: the set-up screen (types, fields, relationships, the defaults)
GET    /commons[?model=]                    the common analyses you may see
POST   /commons                             {store_in, name, description, sides, settings}: make one (background)
GET    /commons/<a>                         one, with its elements, relationships, suggestions and runs
DELETE /commons/<a>
POST   /commons/<a>/refresh                 {settings?}: compare again, maybe with new settings (background)
POST   /commons/<a>/suggestions             {confirm: [[a, b]], reject: [[a, b]]}: close names matched or not, then again
POST   /commons/<a>/items                   {items, decision?, note?}
POST   /commons/<a>/tag                     {items?}: tag the common elements in each side's model (background)
POST   /commons/<a>/make-model              {side, name, description, items?}: a new model of the common part (background)
GET    /commons/<a>/download?format=xlsx|docx[&background=true]
"""

from __future__ import annotations

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint

from .. import commons as co
from ..auth import require_auth
from .models import Free, FreeIn
from .tasks import start, waiting
from .versions import DOCX, XLSX, _file, _read, _write

blp = Blueprint("commons", __name__, url_prefix="/api/v1", description="Common analysis: what models have in common (D286)")
SECURITY = [{"bearerAuth": []}]


def _w(analysis_id, fn, action, details=None):
    model_id = _read(lambda c: co.model_of(c, analysis_id))
    return _write(lambda c: fn(c, model_id), action, model_id, {"analysis": analysis_id, **(details or {})})


@blp.route("/commons/preview")
class Preview(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """The set-up screen for the sides chosen: every entity type with its fields and relationships, the counts per side"""
        return _read(lambda c: co.preview(c, (data or {}).get("sides") or []))


@blp.route("/commons")
class Commons(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The common analyses you may see (stored in models you may read)"""
        return _read(lambda c: co.list_analyses(c, request.args.get("model") or None))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """A new common analysis, stored in the model given (store_in). In the background (D273)"""
        d = data or {}
        if not waiting():
            return start("common.create", d.get("store_in"), f"Make the common analysis '{d.get('name')}'", d, "#/compare/common")
        return _write(lambda c: co.create(c, d.get("store_in"), g.user, d.get("name") or "", d.get("sides") or [], d.get("settings"),
                                          d.get("description") or ""), "common.create", d.get("store_in"), {"name": d.get("name")})


@blp.route("/commons/<string:analysis_id>")
class Common(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, analysis_id):
        return _read(lambda c: co.get(c, co.model_of(c, analysis_id), analysis_id))

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, analysis_id):
        return _w(analysis_id, lambda c, m: co.delete(c, m, g.user, analysis_id), "common.delete")


@blp.route("/commons/<string:analysis_id>/refresh")
class Refresh(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, analysis_id):
        """Compare the sides again (with changed settings, if given); notes and decisions are kept. In the background"""
        if not waiting():
            m = _read(lambda c: co.model_of(c, analysis_id))
            return start("common.refresh", m, "Compare a common analysis again", {"analysis": analysis_id, "settings": (data or {}).get("settings")},
                         f"#/compare/common/{analysis_id}")
        return _w(analysis_id, lambda c, m: co.refresh(c, m, g.user, analysis_id, (data or {}).get("settings")), "common.refresh")


@blp.route("/commons/<string:analysis_id>/suggestions")
class Suggestions(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, analysis_id):
        """Confirm suggested matches (kept for the next run) or reject them (not suggested again); compared again (background)"""
        d = data or {}
        if not waiting():
            m = _read(lambda c: co.model_of(c, analysis_id))
            return start("common.suggestions", m, "Match close names in a common analysis", {"analysis": analysis_id, **d},
                         f"#/compare/common/{analysis_id}")
        return _w(analysis_id, lambda c, m: co.decide_suggestions(c, m, g.user, analysis_id, d.get("confirm"), d.get("reject")), "common.match")


@blp.route("/commons/<string:analysis_id>/items")
class Items(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, analysis_id):
        """A decision or a note for one or many elements"""
        d = data or {}
        return _w(analysis_id, lambda c, m: co.update_items(c, m, g.user, analysis_id, d.get("items") or [], d.get("decision"), d.get("note")),
                  "common.items")


@blp.route("/commons/<string:analysis_id>/tag")
class Tag(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, analysis_id):
        """Tag the common elements (all, or items) in each side's model: one commit per model (background)"""
        d = data or {}
        if not waiting():
            m = _read(lambda c: co.model_of(c, analysis_id))
            return start("common.tag", m, "Tag the common elements", {"analysis": analysis_id, **d}, f"#/compare/common/{analysis_id}")
        return _w(analysis_id, lambda c, m: co.tag_common(c, m, g.user, analysis_id, d.get("items")), "common.tag")


@blp.route("/commons/<string:analysis_id>/make-model")
class MakeModel(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, analysis_id):
        """A new model holding the common elements, copied from one side's model (background)"""
        d = data or {}
        if not waiting():
            m = _read(lambda c: co.model_of(c, analysis_id))
            return start("common.make_model", m, f"Make the model '{d.get('name') or 'of the common part'}'", {"analysis": analysis_id, **d},
                         "#/model-admin")
        return _w(analysis_id, lambda c, m: co.make_model(c, m, g.user, analysis_id, d), "common.make_model")


@blp.route("/commons/<string:analysis_id>/download")
class Download(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "format", "schema": {"type": "string", "enum": ["xlsx", "docx"]}}])
    @require_auth()
    def get(self, analysis_id):
        """The common analysis as an Excel workbook or a Word document (?background=true: as a task)"""
        fmt = "docx" if request.args.get("format") == "docx" else "xlsx"
        if request.args.get("background") == "true":
            m = _read(lambda c: co.model_of(c, analysis_id))
            return start("common.download", m, f"Download a common analysis ({'Word' if fmt == 'docx' else 'Excel'})",
                         {"analysis": analysis_id, "format": fmt}, f"#/compare/common/{analysis_id}")
        a = _read(lambda c: co.get(c, co.model_of(c, analysis_id), analysis_id))
        safe = "".join(ch if ch.isalnum() or ch in " ._-" else "-" for ch in a["name"])[:100].strip() or "common-analysis"
        return _file(co.to_docx(a), f"{safe}.docx", DOCX) if fmt == "docx" else _file(co.to_xlsx(a), f"{safe}.xlsx", XLSX)
