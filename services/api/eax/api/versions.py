"""Model tags, comparison and gap analysis (build phase 8.3, D172).

GET    /models/<m>/tags                         the model's tags (frozen snapshots)
POST   /models/<m>/tags                         tag the model as it is now (content rights)
PATCH  /models/<m>/tags/<t>                     rename, describe, lock (unlock: Model Admin)
DELETE /models/<m>/tags/<t>                     delete an unlocked tag
GET    /models/<m>/tags/<t>/download            the tag as a model package (?format=xlsx|zip)
POST   /models/<m>/tags/<t>/restore             make the tag the latest (Model Admin): the current version is tagged first
POST   /compare/fields                          the filter screen for two sides: types, fields, defaults
POST   /compare                                 compare two sides (models or tags) with the chosen settings
POST   /compare/download                        the comparison as an Excel workbook
GET    /models/<m>/compare-profiles             saved comparison profiles; POST to save one; DELETE .../<p>
GET    /models/<m>/gaps                         the gap analyses kept in the model, the TOGAF templates
POST   /models/<m>/gaps                         a new gap analysis
GET    /models/<m>/gaps/<a>                     one gap analysis with its gaps; DELETE to delete it
POST   /models/<m>/gaps/<a>/refresh             compare again (notes, resolutions and work packages kept)
PATCH  /models/<m>/gaps/<a>/items/<i>           a gap's note, resolution, work packages
POST   /models/<m>/gaps/<a>/items               the same resolution or note for many gaps
POST   /models/<m>/gaps/<a>/gap-entities        add gaps to the model as Gap entities (Model Admin; committed at once)
GET    /models/<m>/gaps/<a>/download            the gap analysis as Excel or Word (?format=xlsx|docx)
"""

from __future__ import annotations

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields
from sqlalchemy.exc import DBAPIError

from .. import audit
from .. import compare as cp
from .. import gaps as gp
from .. import repository as repo
from .. import tags as tg
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .models import Free

blp = Blueprint("versions", __name__, url_prefix="/api/v1",
                description="Model tags (snapshots), comparison and TOGAF gap analysis (phase 8.3)")
SECURITY = [{"bearerAuth": []}]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class TagIn(Schema):
    name = fields.String(required=True)
    description = fields.String(load_default="")
    lock = fields.Boolean(load_default=False)


class TagPatch(Schema):
    name = fields.String(load_default=None)
    description = fields.String(load_default=None)
    locked = fields.Boolean(load_default=None, allow_none=True)


class NoteIn(Schema):
    note = fields.String(load_default="")


class DetailIn(Schema):
    left = fields.Dict(required=True, metadata={"description": "{kind: model|tag, id}: the baseline"})
    right = fields.Dict(required=True, metadata={"description": "{kind: model|tag, id}: the target"})
    left_entity = fields.String(load_default=None, allow_none=True, metadata={"description": "The element's id in the baseline"})
    right_entity = fields.String(load_default=None, allow_none=True, metadata={"description": "The element's id in the target"})


class SidesIn(Schema):
    left = fields.Dict(required=True, metadata={"description": "{kind: model|tag, id}: the baseline"})
    right = fields.Dict(required=True, metadata={"description": "{kind: model|tag, id}: the target"})
    settings = fields.Dict(load_default=None, metadata={"description": "{types: {code: [fields]}, relationship_types: [...], "
                                                                        "metamodel: bool, matches: {left guid: right guid}}"})


class ProfileIn(Schema):
    name = fields.String(required=True)
    settings = fields.Dict(required=True)


class GapIn(Schema):
    store_in = fields.String(required=True, metadata={"description": "The model the gaps are stored in (a project model, not locked)"})
    name = fields.String(required=True)
    description = fields.String(load_default="")
    template = fields.String(load_default="all")
    baseline = fields.Dict(required=True)
    target = fields.Dict(required=True)
    settings = fields.Dict(load_default=None)


class GapItemIn(Schema):
    note = fields.String(load_default=None)
    resolution = fields.String(load_default=None)
    work_packages = fields.List(fields.String(), load_default=None)


class GapItemsIn(Schema):
    items = fields.List(fields.String(), required=True)
    note = fields.String(load_default=None)
    resolution = fields.String(load_default=None)


class GapEntitiesIn(Schema):
    items = fields.List(fields.String(), load_default=None)
    include_kept = fields.Boolean(load_default=False)


def _read(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))


def _write(fn, action: str, object_id, details=None):
    try:
        with get_engine().connect() as conn:
            trans = conn.begin()
            try:
                out = fn(conn)
            except Exception:
                trans.rollback()
                raise
            audit.record(conn, actor=g.user.username, action=action, object_type="model" if object_id else "compare", object_id=str(object_id or ""),
                         details=details or {}, request_id=getattr(g, "request_id", None))
            trans.commit()
            return out
    except EditError as exc:
        abort(exc.status, message=str(exc))
    except repo.NotFound as exc:
        abort(404, message=str(exc))
    except DBAPIError as exc:
        abort(403 if "Not allowed" in str(exc.orig) else 409, message=_db_message(exc))


def _file(data: bytes, name: str, ctype: str) -> Response:
    return Response(data, mimetype=ctype, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------- tags
@blp.route("/models/<uuid:model_id>/tags")
class Tags(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The model's tags, newest first: name, who and when, commit and metamodel version, locked"""
        return _read(lambda c: tg.list_tags(c, model_id))

    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "wait", "schema": {"type": "boolean"},
                                             "description": "true: tag in this request and answer with the tag"}])
    @blp.arguments(TagIn)
    @blp.response(202, Free)
    @require_auth()
    def post(self, data, model_id):
        """Tags the model as it is now: a frozen snapshot of its metamodel and committed content (content rights). On a
        large model this takes a while, so it runs in the background (D192): the answer is a task to follow at
        GET /tasks/<id>, which says when the tag is made. ?wait=true tags in the request instead"""
        name = (data["name"] or "").strip()
        m = _read(lambda c: tg.check_tag(c, model_id, g.user, name))
        if request.args.get("wait") != "true":
            from .. import tasks as tk
            task = None
            try:
                from ..jobs import app as jobs_app
                from ..jobs import run_task
                with get_engine().connect() as conn, conn.begin():
                    task = tk.create(conn, "tag.create", model_id, g.user, f"Tag {m['name']} as '{name}'",
                                     {"name": name, "description": data["description"], "lock": data["lock"]})
                with jobs_app.open():
                    job = run_task.defer(task_id=task["id"], actor=g.user.username, roles=list(g.user.roles))
                with get_engine().connect() as conn, conn.begin():
                    tk.set_job(conn, task["id"], job)
                return {"task": task}
            except Exception:  # noqa: BLE001 - no job runner reachable: tag in this request instead
                import logging
                logging.getLogger(__name__).warning("job runner not reachable; tagging in the request")
                if task:
                    from sqlalchemy import text as sql
                    with get_engine().connect() as conn, conn.begin():
                        conn.execute(sql("DELETE FROM core.tasks WHERE guid = CAST(:g AS uuid)"), {"g": task["id"]})
        return _write(lambda c: tg.create_tag(c, model_id, g.user, name, data["description"], data["lock"]),
                      "tag.create", model_id, {"name": name})


@blp.route("/tags")
class AllTags(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The Tags screen: the tags of every model you may read, newest first"""
        return _read(lambda c: tg.list_all_tags(c))


@blp.route("/models/<uuid:model_id>/tags/<string:tag_id>/entities/<string:entity_id>")
class TagEntity(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, tag_id, entity_id):
        """One entity as it was in the tag: fields, values and relationships"""
        return _read(lambda c: tg.tag_entity(c, model_id, tag_id, entity_id))


@blp.route("/models/<uuid:model_id>/tags/<string:tag_id>")
class Tag(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, tag_id):
        """One tag: its details and its frozen contents (entities by type, relationships, the metamodel in short)"""
        return _read(lambda c: tg.get_tag(c, model_id, tag_id))

    @blp.doc(security=SECURITY)
    @blp.arguments(TagPatch)
    @blp.response(200, Free)
    @require_auth()
    def patch(self, data, model_id, tag_id):
        """Renames or describes a tag (not when locked), locks it, or unlocks it (Model Admin)"""
        return _write(lambda c: tg.update_tag(c, model_id, g.user, tag_id, data.get("name"), data.get("description"),
                                              data.get("locked")), "tag.update", model_id, {"tag": tag_id})

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, model_id, tag_id):
        """Deletes a tag that is not locked"""
        return _write(lambda c: tg.delete_tag(c, model_id, g.user, tag_id), "tag.delete", model_id, {"tag": tag_id})


@blp.route("/models/<uuid:model_id>/tags/<string:tag_id>/download")
class TagDownload(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "format", "schema": {"type": "string", "enum": ["xlsx", "zip"]}}])
    @require_auth()
    def get(self, model_id, tag_id):
        """The tag as a model package (Excel or zip): to keep, load elsewhere, or merge into another model"""
        fmt = "zip" if request.args.get("format") == "zip" else "xlsx"
        if request.args.get("background") == "true":   # D273: made in the background, downloaded from the task
            from .tasks import start
            return start("tag.download", model_id, f"Download a tag ({fmt})", {"tag": tag_id, "format": fmt},
                         f"#/metamodel/{model_id}/tags")
        data, name, ctype = _read(lambda c: tg.download_tag(c, model_id, tag_id, fmt, g.user.username))
        return _file(data, name, ctype)


@blp.route("/models/<uuid:model_id>/tags/<string:tag_id>/restore")
class TagRestore(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(NoteIn)
    @blp.response(200, Free)
    @require_auth("model.lock")
    def post(self, data, model_id, tag_id):
        """Makes the tag the latest (Model Admin): the current version is tagged first, then the tag overwrites the
        model completely, metamodel and content, as one commit. Restore that new tag to go back. In the background (D273)"""
        from .tasks import start, waiting
        if not waiting():
            return start("tag.restore", model_id, "Restore a tag as the latest", {"tag": tag_id, "note": data.get("note", "")},
                         f"#/metamodel/{model_id}/tags")
        return _write(lambda c: tg.restore_tag(c, model_id, g.user, tag_id, data.get("note", "")), "tag.restore", model_id,
                      {"tag": tag_id})


# ---------------------------------------------------------------- comparison
@blp.route("/compare/fields")
class CompareFields(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(SidesIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """The filter screen: every entity type of either side with its fields, the tool's defaults, the relationship types"""
        def run(c):
            info = cp.fields_for(cp.load_side(c, data["left"]), cp.load_side(c, data["right"]))
            return {**info, "defaults": cp.defaults(info)}
        return _read(run)


@blp.route("/compare")
class Compare(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(SidesIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """Compares two sides (each a model as it is now, or a tag): summary, entities, fields, relationships, metamodel.
        In the background (D273): the answer is a task whose result is the comparison; ?wait=true compares in the request"""
        from .tasks import start, waiting
        if not waiting():
            return start("compare.run", None, "Compare two sides", data, "#/compare")
        return _read(lambda c: cp.compare(cp.load_side(c, data["left"]), cp.load_side(c, data["right"]), data.get("settings")))


@blp.route("/compare/download")
class CompareDownload(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(SidesIn)
    @require_auth()
    def post(self, data):
        """The comparison as an Excel workbook: summary, entities, field changes, relationships, metamodel.
        In the background (D273): the answer is a task with the file; ?wait=true answers the file"""
        from .tasks import start, waiting
        if not waiting():
            return start("compare.download", None, "Download a comparison (Excel)", data, "#/compare")
        res = _read(lambda c: cp.compare(cp.load_side(c, data["left"]), cp.load_side(c, data["right"]), data.get("settings")))
        name = f"Compare {res['left']['label']} with {res['right']['label']}"
        safe = "".join(ch if ch.isalnum() or ch in " ._-" else "-" for ch in name)[:120].strip()
        return _file(cp.to_xlsx(res, name), f"{safe}.xlsx", XLSX)


@blp.route("/compare/detail")
class CompareDetail(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(DetailIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """One element side by side: {left, right (sides), left_entity, right_entity}; every field, value and relationship"""
        def run(c):
            return cp.entity_detail(cp.load_side(c, data["left"]), cp.load_side(c, data["right"]),
                                    data.get("left_entity"), data.get("right_entity"))
        return _read(run)


# ---------------------------------------------------------------- comparison profiles (shared by everyone, D177)
@blp.route("/compare-profiles")
class Profiles(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The saved comparison profiles (everyone's)"""
        return _read(lambda c: cp.list_profiles(c))

    @blp.doc(security=SECURITY)
    @blp.arguments(ProfileIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """Saves a comparison profile for everyone (the same name again, by its maker, replaces it)"""
        return _write(lambda c: cp.save_profile(c, g.user, data["name"], data["settings"]), "compare.profile_save", None,
                      {"name": data["name"]})


@blp.route("/compare-profiles/<string:profile_id>")
class Profile(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, profile_id):
        """Deletes a profile (its maker or a Super Admin)"""
        return _write(lambda c: cp.delete_profile(c, g.user, profile_id), "compare.profile_delete", None, {"profile": profile_id})


# ---------------------------------------------------------------- gap analyses (first-class, D177): stored in a model you choose
def _gap_write(analysis_id, fn, action: str, details=None):
    model_id = _read(lambda c: gp.model_of(c, analysis_id))
    return _write(lambda c: fn(c, model_id), action, model_id, {"analysis": analysis_id, **(details or {})})


@blp.route("/gaps")
class Gaps(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "model", "schema": {"type": "string"},
                                             "description": "Only those stored in this model"}])
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The gap analyses you may see (stored in models you may read), and the TOGAF templates and resolutions"""
        return _read(lambda c: gp.list_analyses(c, request.args.get("model") or None))

    @blp.doc(security=SECURITY)
    @blp.arguments(GapIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """A new gap analysis: a baseline and a target (any models you may read, as they are now or a tag of each) compared
        with a TOGAF template, the gaps stored in the model given (store_in). In the background (D273)"""
        from .tasks import start, waiting
        if not waiting():
            return start("gap.create", data["store_in"], f"Make the gap analysis '{data['name']}'", data, "#/compare/gaps")
        return _write(lambda c: gp.create(c, data["store_in"], g.user, data["name"], data["baseline"], data["target"], data["template"],
                                          data.get("settings"), data["description"]), "gap.create", data["store_in"], {"name": data["name"]})


@blp.route("/gaps/<string:analysis_id>")
class Gap(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, analysis_id):
        """One gap analysis: the model it is stored in, its sides, when compared, the gaps with their decisions and its results"""
        return _read(lambda c: gp.get(c, gp.model_of(c, analysis_id), analysis_id))

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, analysis_id):
        return _gap_write(analysis_id, lambda c, m: gp.delete(c, m, g.user, analysis_id), "gap.delete")


@blp.route("/gaps/<string:analysis_id>/refresh")
class GapRefresh(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, analysis_id):
        """Compares the two sides again; the gaps' notes, resolutions, work packages and Gap entities are kept.
        In the background (D273)"""
        from .tasks import start, waiting
        if not waiting():
            model_id = _read(lambda c: gp.model_of(c, analysis_id))
            return start("gap.refresh", model_id, "Compare a gap analysis again", {"analysis": analysis_id},
                         f"#/compare/gaps/{analysis_id}")
        return _gap_write(analysis_id, lambda c, m: gp.refresh(c, m, g.user, analysis_id), "gap.refresh")


@blp.route("/gaps/<string:analysis_id>/items/<string:item_id>")
class GapItem(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(GapItemIn)
    @blp.response(200, Free)
    @require_auth()
    def patch(self, data, analysis_id, item_id):
        """A gap's note, resolution and work packages (entities of the storage model)"""
        return _gap_write(analysis_id, lambda c, m: gp.update_item(c, m, g.user, analysis_id, item_id, data.get("note"),
                                                                   data.get("resolution"), data.get("work_packages")),
                          "gap.item", {"item": item_id})


@blp.route("/gaps/<string:analysis_id>/items/<string:item_id>/detail")
class GapItemDetail(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, analysis_id, item_id):
        """One gap side by side: the element in the baseline and in the target, the differences marked"""
        return _read(lambda c: gp.item_detail(c, gp.model_of(c, analysis_id), analysis_id, item_id))


@blp.route("/gaps/<string:analysis_id>/items")
class GapItems(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(GapItemsIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, analysis_id):
        """The same resolution or note for many gaps at once"""
        return _gap_write(analysis_id, lambda c, m: gp.update_items(c, m, g.user, analysis_id, data["items"], data.get("resolution"),
                                                                    data.get("note")), "gap.items")


@blp.route("/gaps/<string:analysis_id>/gap-entities")
class GapEntities(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(GapEntitiesIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, analysis_id):
        """Adds gaps to the storage model as Gap entities (its Model Admins; one commit at once; a Gap entity type is added if needed)"""
        return _gap_write(analysis_id, lambda c, m: gp.add_gap_entities(c, m, g.user, analysis_id, data.get("items"), data["include_kept"]),
                          "gap.entities")


@blp.route("/gaps/<string:analysis_id>/download")
class GapDownload(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "format", "schema": {"type": "string", "enum": ["xlsx", "docx"]}}])
    @require_auth()
    def get(self, analysis_id):
        """The gap analysis as an Excel workbook (gaps, TOGAF gap matrix, field changes) or a Word document.
        ?background=true: made in the background (D273), downloaded from the task"""
        if request.args.get("background") == "true":
            from .tasks import start
            fmt = "docx" if request.args.get("format") == "docx" else "xlsx"
            model_id = _read(lambda c: gp.model_of(c, analysis_id))
            return start("gap.download", model_id, f"Download a gap analysis ({'Word' if fmt == 'docx' else 'Excel'})",
                         {"analysis": analysis_id, "format": fmt}, f"#/compare/gaps/{analysis_id}")
        a = _read(lambda c: gp.get(c, gp.model_of(c, analysis_id), analysis_id))
        safe = "".join(ch if ch.isalnum() or ch in " ._-" else "-" for ch in a["name"])[:100].strip() or "gap-analysis"
        if request.args.get("format") == "docx":
            return _file(gp.to_docx(a), f"{safe}.docx", DOCX)
        return _file(gp.to_xlsx(a), f"{safe}.xlsx", XLSX)


# ---------------------------------------------------------------- gap results (runs) and comparing two of them
@blp.route("/gap-runs")
class GapRuns(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "model", "schema": {"type": "string"}},
                                            {"in": "query", "name": "analysis", "schema": {"type": "string"}},
                                            {"in": "query", "name": "q", "schema": {"type": "string"}}])
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Every result of every gap analysis you may see (each time one was made or compared again), newest first"""
        return _read(lambda c: gp.list_runs(c, request.args.get("model") or None, request.args.get("q") or None,
                                            request.args.get("analysis") or None))


@blp.route("/gap-runs/<run_id>")
class GapRun(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, run_id):
        """Delete one result of a gap analysis (the analysis, its gaps, notes and other results stay)"""
        info = _read(lambda c: gp.run_info(c, run_id))
        return _write(lambda c: gp.delete_run(c, info["model"], g.user, run_id), "gap.run_delete", info["model"],
                      {"name": info["name"], "result": run_id})


@blp.route("/gap-runs/compare")
class GapRunsCompare(MethodView):
    @blp.doc(security=SECURITY, parameters=[{"in": "query", "name": "a", "required": True, "schema": {"type": "string"}},
                                            {"in": "query", "name": "b", "required": True, "schema": {"type": "string"}},
                                            {"in": "query", "name": "format", "schema": {"type": "string", "enum": ["xlsx", "csv", "json"]}}])
    @require_auth()
    def get(self):
        """Two gap results side by side (gaps closed, new gaps, status or resolution changed) as an Excel workbook; not kept"""
        a, b = request.args.get("a"), request.args.get("b")
        if not a or not b:
            abort(400, message="Choose two gap results to compare (a and b).")
        if request.args.get("background") == "true" and request.args.get("format") != "json":   # D273
            from .tasks import start
            fmt = "csv" if request.args.get("format") == "csv" else "xlsx"
            return start("gap.runs_compare", None, f"Compare two gap results ({fmt})", {"a": a, "b": b, "format": fmt},
                         f"#/compare/gaps/results?a={a}&b={b}")
        res = _read(lambda c: gp.compare_runs(c, a, b))
        if request.args.get("format") == "json":
            return res
        if request.args.get("format") == "csv":
            return _file(gp.runs_to_csv(res), "gap-results-compared.csv", "text/csv; charset=utf-8")
        return _file(gp.runs_to_xlsx(res), "gap-results-compared.xlsx", XLSX)
