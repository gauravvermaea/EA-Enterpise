"""Validation and data quality (build phase 12, D239).

GET  /models/<m>/quality                         the model's quality now: score, by type and owner, findings, trend, rules
POST /models/<m>/quality/run                     measure in the background and keep it (VAL-003, D245); POST /quality/run: all
GET  /models/<m>/quality/jobs                    measurements queued, running and last finished
GET  /models/<m>/entities/<e>/quality            one entity's quality now, field by field (D246)
GET  /models/<m>/quality/types[/<type>]          each entity type's quality now; one type's entities (grids)
GET|POST /models/<m>/quality/not-applicable      fields not applicable on one entity; POST .../<id>/approve|reject|withdraw
GET  /models/<m>/quality/runs                    the kept measurements (the trend)
PUT  /models/<m>/quality/settings                {stale_days, cron, weights, score_parts, bands}: a Model Admin's change
                                                 waits for a Super Admin
POST /models/<m>/quality/rules                   add or change a rule (same approval)
POST /models/<m>/quality/rules/preview           what a rule would find now, without keeping it
POST /models/<m>/quality/rules/<code>/delete     delete one of the model's own rules (same approval)
POST /models/<m>/quality/seal                    {entities, kind: seal | current, note}: attest, or mark still current
POST /models/<m>/quality/unseal                  {entities}: remove seals (Model Admins)
GET  /models/<m>/quality/pdf                     every metric as a PDF (?drill=...&value=...: one drill-down's entities)
GET  /quality                                    the estate: overall score and trend, every model (Super and IT Admins: all)
GET  /quality/pdf                                the estate as a PDF
GET  /models/<m>/quality/xlsx, /quality/xlsx     the same as Excel workbooks, the drill-downs as Excel groups
PUT  /quality/scope                              {models, measured}: which models are measured (Super and IT Admins)
GET  /quality/defaults, PUT /quality/defaults    the installation's stale period, schedule, score weights and colours
                                                 (D244; Super Admins change them)
GET  /quality/changes                            quality changes waiting for approval (Super Admins)
POST /quality/changes/<id>/approve|reject        {note}
"""

from __future__ import annotations

import logging

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy.exc import DBAPIError

from .. import quality as q
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .models import Free, FreeIn

log = logging.getLogger(__name__)

blp = Blueprint("quality", __name__, url_prefix="/api/v1", description="Validation and data quality (phase 12)")
SECURITY = [{"bearerAuth": []}]


def _read(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _file(data: bytes, filename: str, mimetype: str) -> Response:
    return Response(data, mimetype=mimetype, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _pdf(data: bytes, filename: str) -> Response:
    return _file(data, filename, "application/pdf")


def _write(fn):
    try:
        with get_engine().begin() as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))
    except DBAPIError as exc:
        abort(409, message=_db_message(exc))


@blp.route("/models/<uuid:model_id>/quality")
class Quality(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The model's quality now (measured when asked), its trend, settings, rules and changes waiting for approval"""
        return _read(lambda c: {**q.dashboard(c, model_id), "may_manage": q.is_model_admin(c, g.user, repo.get_model(c, model_id))})


@blp.route("/models/<uuid:model_id>/quality/pdf")
class QualityPdf(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, model_id):
        """Every data quality metric of the model as a PDF; with ?drill=type|owner|rule|kind|mine|all&value=..., only the
        entities of that drill-down"""
        from .. import quality_pdf
        drill, value = request.args.get("drill", ""), request.args.get("value", "")
        data = _read(lambda c: q.dashboard(c, model_id))
        name = "".join(ch if ch.isalnum() else "-" for ch in data["model"]["name"]).strip("-")
        return _pdf(quality_pdf.model_pdf(data, drill, value, g.user.username),
                    f"{name}-data-quality{'-' + drill if drill else ''}.pdf")


@blp.route("/models/<uuid:model_id>/quality/xlsx")
class QualityXlsx(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, model_id):
        """Every data quality metric of the model as an Excel workbook, the drill-downs as Excel groups (type, owner and rule
        open to their entities, each entity to its findings); with ?drill=...&value=..., only that drill-down's entities"""
        from .. import quality_xlsx
        drill, value = request.args.get("drill", ""), request.args.get("value", "")
        data = _read(lambda c: q.dashboard(c, model_id))
        name = "".join(ch if ch.isalnum() else "-" for ch in data["model"]["name"]).strip("-")
        return _file(quality_xlsx.model_xlsx(data, request.host_url, drill, value, g.user.username),
                     f"{name}-data-quality{'-' + drill if drill else ''}.xlsx", XLSX)


@blp.route("/models/<uuid:model_id>/quality/run")
class QualityRun(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, model_id):
        """Measure the model's quality in the background and keep the measurement (Measure now, Recalculate; D245): returns
        the request at once; GET .../quality/jobs (or the Quality tab) shows when it is done, and the asker is told"""
        r = _write(lambda c: q.request_run(c, model_id, g.user))
        return _start([r])[0]


def _start(reqs: list[dict]) -> list[dict]:
    """Defers the background job of each new request; without a reachable job runner, measures in this request instead."""
    new = [r for r in reqs if r.get("new")]
    if new:
        try:
            from ..jobs import app as jobs_app
            from ..jobs import quality_measure
            with jobs_app.open():
                for r in new:
                    quality_measure.defer(request_id=r["id"])
            for r in reqs:
                r["status"] = "queued"
            return reqs
        except Exception:  # noqa: BLE001 - no job runner: measure now
            log.warning("job runner not reachable; measuring quality in the request")
            for r in new:
                q.run_request(lambda: get_engine().begin(), r["id"])
                r["status"] = "done"
    return reqs


@blp.route("/models/<uuid:model_id>/quality/jobs")
class QualityJobs(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The model's measurements queued, running and last finished (D245)"""
        return _read(lambda c: {"jobs": q.jobs(c, repo.get_model(c, model_id))})


@blp.route("/quality/run")
class QualityRunAll(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self):
        """Measure all: every model that is measured (and that you may read) in the background, one job each (D245)"""
        def go(c):
            return [q.request_run(c, m["id"], g.user) for m in q.installation(c, g.user)["models"]]
        return {"requests": _start(_write(go))}


@blp.route("/models/<uuid:model_id>/entities/<string:entity>/quality")
class EntityQuality(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, entity):
        """One entity's data quality now: score, parts, and per field why it lowers it (D246)"""
        return _read(lambda c: {**q.entity_quality(c, model_id, entity),
                                "may_approve": q.is_model_admin(c, g.user, repo.get_model(c, model_id))})


@blp.route("/models/<uuid:model_id>/entities/<string:entity>/quality/recheck")
class EntityRecheck(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, model_id, entity):
        """Recheck one entity's data quality now and store it (the ↻ on a row)"""
        return _write(lambda c: q.recheck_entity(c, model_id, entity))


@blp.route("/models/<uuid:model_id>/quality/types/<string:entity_type>/recheck")
class TypeRecheck(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, model_id, entity_type):
        """Recheck every entity of a type in the background (Recheck all; a task followed in the task drawer, D273)"""
        from .tasks import start, waiting
        if not waiting():
            return start("quality.recheck_type", model_id, f"Recheck data quality of {entity_type}",
                         {"entity_type": entity_type}, f"#/metamodel/{model_id}/quality")
        return _write(lambda c: q.recheck_type(c, model_id, entity_type))


@blp.route("/models/<uuid:model_id>/quality/types")
class TypeScores(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Every entity type's overall data quality now"""
        return _read(lambda c: q.type_scores(c, model_id))


@blp.route("/models/<uuid:model_id>/quality/types/<string:entity_type>")
class TypeQuality(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id, entity_type):
        """One entity type's data quality now, and each of its entities' with the fields that lower it (grids)"""
        return _read(lambda c: q.type_quality(c, model_id, entity_type))


@blp.route("/models/<uuid:model_id>/quality/leave-out")
class LeaveOut(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """{item: attr:<code> | field:description, entity_type: * | <code>, include: false}: a Model Admin leaves a field out
        of data quality for the whole model (applies at once, the Super Admins are told); include=true counts it again"""
        data = data or {}
        return _write(lambda c: q.leave_out(c, model_id, g.user, data.get("item"), data.get("entity_type") or "*",
                                            bool(data.get("include"))))


@blp.route("/models/<uuid:model_id>/quality/not-applicable")
class NotApplicable(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """Fields marked not applicable on one entity: waiting (?status=pending, the default), approved or all (status=)"""
        status = request.args.get("status", "pending")
        return _read(lambda c: {"exemptions": q.exemptions(c, repo.get_model(c, model_id), status),
                                "may_approve": q.is_model_admin(c, g.user, repo.get_model(c, model_id))})

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """{entity, item: attr:<code> | field:description, reason}: mark it not applicable on that entity (D246); a Model
        Admin approves it (theirs applies at once)"""
        data = data or {}
        return _write(lambda c: q.request_exemption(c, model_id, g.user, str(data.get("entity") or ""), data.get("item"),
                                                    data.get("reason")))


@blp.route("/models/<uuid:model_id>/quality/not-applicable/decide")
class NotApplicableDecideMany(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """{ids, decision: approve | reject, note}: decide many 'not applicable' requests at once (Model Admins)"""
        data = data or {}
        return _write(lambda c: q.decide_exemptions(c, model_id, g.user, list(data.get("ids") or []), data.get("decision") or "",
                                                    data.get("note") or ""))


@blp.route("/quality/changes/decide")
class QualityDecideMany(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data):
        """{ids, decision: approve | reject, note}: decide many Model Admins' quality changes at once (Super Admins)"""
        data = data or {}
        return _write(lambda c: q.decide_many(c, g.user, list(data.get("ids") or []), data.get("decision") == "approve",
                                              data.get("note") or ""))


@blp.route("/quality/changes/<uuid:change_id>/resubmit")
class QualityResubmit(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, change_id):
        """Ask again for a rejected quality change {note, payload?}: it waits for a Super Admin again"""
        data = data or {}
        return _write(lambda c: q.resubmit_change(c, g.user, str(change_id), data.get("note") or "", data.get("payload")))


@blp.route("/models/<uuid:model_id>/quality/not-applicable/<uuid:exemption_id>/<string:decision>")
class NotApplicableDecide(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id, exemption_id, decision):
        """approve, reject (Model Admins) or withdraw (the asker or a Model Admin) {note}"""
        return _write(lambda c: q.decide_exemption(c, model_id, g.user, str(exemption_id), decision, (data or {}).get("note", "")))


@blp.route("/models/<uuid:model_id>/quality/runs")
class QualityRuns(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The kept measurements, newest first"""
        return _read(lambda c: {"runs": q.runs(c, model_id)})


@blp.route("/models/<uuid:model_id>/quality/settings")
class QualitySettings(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, model_id):
        """The model's own stale period, schedule, weights, score weights {completeness, rules, freshness} adding up to 100
        and colours {green, amber} (empty or null: inherited). A Model Admin's change waits for a Super
        Admin's approval; a Super Admin's applies at once"""
        data = data or {}
        return _write(lambda c: q.change(c, model_id, g.user, "settings", data, data.get("note") or ""))


@blp.route("/models/<uuid:model_id>/quality/rules")
class QualityRules(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Add or change a rule {code, name, kind, entity_type, spec, severity, enabled, message} (same approval)"""
        data = data or {}
        return _write(lambda c: q.change(c, model_id, g.user, "rule", data, data.get("note") or ""))


@blp.route("/models/<uuid:model_id>/quality/rules/preview")
class QualityRulePreview(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """What a rule would find in the model now, without keeping it"""
        return _read(lambda c: q.preview_rule(c, model_id, data or {}))


@blp.route("/models/<uuid:model_id>/quality/rules/<string:code>/delete")
class QualityRuleDelete(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id, code):
        """Delete one of the model's own rules (same approval)"""
        return _write(lambda c: q.change(c, model_id, g.user, "rule.delete", {"code": code}, (data or {}).get("note") or ""))


@blp.route("/models/<uuid:model_id>/quality/seal")
class QualitySeal(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Attest entities as correct (kind seal: their responsible person or a Model Admin) or mark them still current
        (kind current: a Model Admin, one or many in one click)"""
        data = data or {}
        return _write(lambda c: q.seal(c, model_id, g.user, list(data.get("entities") or []), data.get("kind") or "seal",
                                       data.get("note") or ""))


@blp.route("/models/<uuid:model_id>/quality/unseal")
class QualityUnseal(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, model_id):
        """Remove the seals of entities (Model Admins)"""
        return _write(lambda c: q.unseal(c, model_id, g.user, list((data or {}).get("entities") or [])))


@blp.route("/quality")
class QualityAll(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The estate's quality: its overall score (each model weighs its entities) and weekly trend, and every project model
        with its latest score, a month before and its trend (Super Admins and IT Admins: every model)"""
        from .. import permissions as perms
        return _read(lambda c: {**q.installation(c, g.user), "super_admin": perms.SUPER_ADMIN in g.user.roles})


@blp.route("/quality/pdf")
class QualityAllPdf(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self):
        """The estate's quality as a PDF"""
        from .. import quality_pdf
        data = _read(lambda c: q.installation(c, g.user))
        return _pdf(quality_pdf.installation_pdf(data), "EA-Explorer-data-quality-estate.pdf")


@blp.route("/quality/xlsx")
class QualityAllXlsx(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self):
        """The estate's quality as an Excel workbook: the estate, every model (each opens to its entity types) and the trend"""
        from .. import quality_xlsx
        data = _read(lambda c: q.installation(c, g.user))
        return _file(quality_xlsx.estate_xlsx(data, request.host_url), "EA-Explorer-data-quality-estate.xlsx", XLSX)


@blp.route("/quality/defaults")
class QualityDefaults(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The installation's data quality defaults: stale period, schedule, score weights and colours (D244)"""
        return _read(lambda c: q.defaults(c))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data):
        """Change the installation's defaults {stale_days, cron, score_parts {completeness, rules, freshness} adding up to
        100, bands {green, amber}} (Super Admins; applies at once and every model inherits what it does not set)"""
        return _write(lambda c: q.set_defaults(c, g.user, data or {}))


@blp.route("/quality/scope")
class QualityScope(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data):
        """Choose which models are measured {models: [guid], measured: true|false}; the choice stays (Super and IT Admins)"""
        data = data or {}
        return _write(lambda c: q.set_scope(c, g.user, list(data.get("models") or []), bool(data.get("measured"))))


@blp.route("/quality/changes")
class QualityChanges(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Quality settings and rules changed by Model Admins: waiting for approval first, then decided (Super Admins)"""
        return _read(lambda c: {"changes": q.pending(c, g.user)})


@blp.route("/quality/changes/<uuid:change_id>/<string:decision>")
class QualityDecide(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, change_id, decision):
        """Approve (apply) or reject a Model Admin's quality change {note}; they are told (Super Admins)"""
        if decision not in ("approve", "reject"):
            abort(404, message="approve or reject")
        return _write(lambda c: q.decide(c, g.user, str(change_id), decision == "approve", (data or {}).get("note") or ""))
