"""Model wizards (phase 13.0.4, D283): the routes the wizards add (the rest use the model screens' own routes).

GET  /models/<m>/wizards/family                 parent, children, the library model it came from, frozen or not
POST /models/<m>/wizards/tag-first              {why}: tag the model before a wizard changes it
POST /models/<m>/wizards/merge                  {source, merge, decisions, all_conflicts, exclude, tag_first,
                                                 freeze_source}: merge `source` into this model choosing what goes in
                                                 (merge into the parent, propagate to a child, library updates);
                                                 a background task. Plan it first with POST /models/<m>/merges
POST /models/<m>/freeze {note} · /unfreeze (Super Admins)
POST /models/<m>/detach · /reparent {parent}
POST /models/<m>/split                          {name, description, child, move, entity_types, entities} (background)
GET  /models/<m>/extend-preview?source=<model>  what another model's metamodel has that this one lacks
POST /models/<m>/extend                         {source, entity_types, relationship_types, attributes} (background)
GET  /models/<m>/duplicates?type=&attributes=&closeness=&names=   groups of likely duplicate entities (phase 21, D361)
GET  /models/<m>/duplicates/xlsx?...              the same as an Excel workbook (D541)
POST /models/<m>/duplicates/merge               {keep, others, choices}: choices {field code: entity whose value is kept}
POST /models/<m>/hand-over                      {add, remove, owner}
"""

from __future__ import annotations

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy.exc import DBAPIError

from .. import audit
from .. import model_wizards as mw
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .models import Free, FreeIn
from .tasks import start, waiting

blp = Blueprint("model_wizards", __name__, url_prefix="/api/v1", description="Model wizards (D283)")
SECURITY = [{"bearerAuth": []}]


def _read(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))


def _write(fn, action: str, model_id, details=None):
    try:
        with get_engine().connect() as conn, conn.begin():
            out = fn(conn)
            audit.record(conn, actor=g.user.username, action=action, object_type="model", object_id=str(model_id),
                         details=details or {}, request_id=getattr(g, "request_id", None))
            return out
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))
    except DBAPIError as exc:
        abort(403 if "Not allowed" in str(exc.orig) else 409, message=_db_message(exc))


@blp.route("/models/<uuid:model_id>/wizards/family")
class Family(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The model's family: parent, children, the library model it came from, frozen or not"""
        return _read(lambda c: mw.family(c, model_id))


@blp.route("/models/<uuid:model_id>/wizards/tag-first")
class TagFirst(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, model_id):
        """Tag the model as it is now, before a wizard changes it"""
        return _write(lambda c: mw.tag_first(c, model_id, g.user, (data or {}).get("why") or "a change"), "tag.created", model_id)


@blp.route("/models/<uuid:model_id>/wizards/merge")
class WizardMerge(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Merge another model into this one with what the person chose (a background task)"""
        d = data or {}
        if not d.get("merge"):
            abort(400, message="Plan the merge first (POST /models/<m>/merges with source_model).")
        return start("wizard.merge", model_id, d.get("label") or "Merge with the model wizard", d, f"#/metamodel/{model_id}/changes")


@blp.route("/models/<uuid:model_id>/freeze")
class Freeze(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Freeze the model: read only for good (Model Admin); a Super Admin unfreezes it"""
        return _write(lambda c: mw.freeze(c, model_id, g.user, (data or {}).get("note", "")), "model.frozen", model_id)


@blp.route("/models/<uuid:model_id>/unfreeze")
class Unfreeze(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, model_id):
        """Unfreeze the model (Super Admins)"""
        return _write(lambda c: mw.unfreeze(c, model_id, g.user), "model.unfrozen", model_id)


@blp.route("/models/<uuid:model_id>/detach")
class Detach(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, model_id):
        """Break the parent-child link: the model becomes one of its own"""
        return _write(lambda c: mw.detach(c, model_id, g.user), "model.detached", model_id)


@blp.route("/models/<uuid:model_id>/reparent")
class Reparent(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Make the model derive from another project model"""
        return _write(lambda c: mw.reparent(c, model_id, g.user, (data or {}).get("parent")), "model.reparented", model_id, data)


@blp.route("/models/<uuid:model_id>/split")
class Split(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Part of the model into a new model (child or separate; copied or moved). In the background"""
        d = data or {}
        if not waiting():
            return start("wizard.split", model_id, f"Split into '{d.get('name') or 'a new model'}'", d, "#/metamodel")
        return _write(lambda c: mw.split(c, model_id, g.user, d), "model.split", model_id)


@blp.route("/models/<uuid:model_id>/extend-preview")
class ExtendPreview(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """What another model's metamodel has that this one lacks"""
        src = request.args.get("source")
        if not src:
            abort(400, message="Choose the model to take metamodel parts from (?source=).")
        return _read(lambda c: mw.extend_preview(c, model_id, src))


@blp.route("/models/<uuid:model_id>/extend")
class Extend(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Add parts of another model's metamodel (Model Admin). In the background"""
        d = data or {}
        if not waiting():
            return start("wizard.extend", model_id, "Extend the metamodel", d, f"#/metamodel/{model_id}/metamodel")
        return _write(lambda c: mw.extend_metamodel(c, model_id, g.user, d.get("source"), d), "metamodel.extended", model_id)


@blp.route("/models/<uuid:model_id>/duplicates")
class Duplicates(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Groups of entities that look like the same thing"""
        a = request.args
        attrs = [x for x in (a.get("attributes") or "").split(",") if x.strip()]
        try:
            closeness = float(a.get("closeness") or 0.88)
        except ValueError:
            closeness = 0.88
        by_name = a.get("names", "true") != "false" or not attrs
        return _read(lambda c: mw.duplicates(c, model_id, a.get("type") or None, closeness, attrs, by_name))


@blp.route("/models/<uuid:model_id>/duplicates/xlsx")
class DuplicatesXlsx(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, model_id):
        """The likely duplicates as an Excel workbook (same arguments as the list; D541)"""
        from flask import Response

        from .. import dedupe
        a = request.args
        attrs = [x for x in (a.get("attributes") or "").split(",") if x.strip()]
        try:
            closeness = float(a.get("closeness") or 0.88)
        except ValueError:
            closeness = 0.88
        by_name = a.get("names", "true") != "false" or not attrs

        def build(c):
            res = mw.duplicates(c, model_id, a.get("type") or None, closeness, attrs, by_name)
            m = repo.get_model(c, model_id)
            return dedupe.to_xlsx(res, m["name"], request.host_url, a.get("type") or ""), m["name"]
        data, name = _read(build)
        safe = "".join(ch if ch.isalnum() or ch in " -_" else "-" for ch in name).strip() or "model"
        return Response(data, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{safe} - likely duplicates.xlsx"'})


@blp.route("/models/<uuid:model_id>/duplicates/merge")
class DuplicatesMerge(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Merge duplicates into the one kept (one commit, which can be rolled back)"""
        d = data or {}
        return _write(lambda c: mw.merge_duplicates(c, model_id, g.user, d.get("keep"), d.get("others") or [], d.get("choices")),
                      "entities.merged", model_id, d)


@blp.route("/models/<uuid:model_id>/hand-over")
class HandOver(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Hand the model over: Model Admins in and out, the owner"""
        d = data or {}
        return _write(lambda c: mw.hand_over(c, model_id, g.user, d.get("add") or [], d.get("remove") or [], d.get("owner")),
                      "model.handed_over", model_id, d)
