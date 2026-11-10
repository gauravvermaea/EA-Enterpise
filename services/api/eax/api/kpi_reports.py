"""KPI trends, the report designer and the OData feed (phase 24, D365, D430 to D435).

GET  /models/<m>/kpis                                 every snapshot kept and the value now, by KPI (the model page's trends)
POST /models/<m>/kpis/definitions                     a Model Admin's own KPI {name, kind, entity_type_code, attribute_code,
                                                      filter_attribute, filter_op, filter_value, unit, description}
PUT  /models/<m>/kpis/definitions/<kpi>               change it; POST .../<kpi>/delete: no longer kept (its trend stays)
GET  /models/<m>/report-designer                      what the designer offers (types, columns, related types), the designs
                                                      and the model's OData feed address
POST /models/<m>/report-designs                       {name, spec}: keep a design; PUT .../<d>: change; POST .../<d>/delete
POST /models/<m>/report-designs/preview               {spec}: the first rows and the SQL, without keeping it

The OData feed (read only, signed in, the person's permissions):
GET  /api/v1/odata/models/<m>/                        the service document
GET  /api/v1/odata/models/<m>/$metadata               the tables and their columns
GET  /api/v1/odata/models/<m>/<Table>                 rows: $select, $filter, $orderby, $top, $skip, $count
"""

from __future__ import annotations

from flask import Blueprint as FlaskBlueprint
from flask import Response, g, jsonify, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy.exc import DBAPIError

from .. import kpis
from .. import odata as od
from .. import report_designer as rd
from .. import repository as repo
from ..auth import require_auth
from ..config import get_settings
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from ..odata_auth import signed_in
from .models import Free, FreeIn

blp = Blueprint("kpi_reports", __name__, url_prefix="/api/v1", description="KPI trends and the report designer (phase 24)")
SECURITY = [{"bearerAuth": []}]


def _read(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404), message=str(exc))


def _write(fn):
    try:
        with get_engine().begin() as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404) if isinstance(exc, repo.NotFound) else getattr(exc, "status", 400), message=str(exc))
    except DBAPIError as exc:
        abort(409, message=_db_message(exc))


@blp.route("/models/<uuid:model_id>/kpis")
class Kpis(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """The model's KPI trends: the standard set and its own KPIs, every snapshot kept (monthly and on tags) and the
        value now"""
        return _read(lambda c: kpis.trends(c, model_id, g.user))


@blp.route("/models/<uuid:model_id>/kpis/definitions")
class KpiDefinitions(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, body, model_id):
        """Add one of the model's own KPIs (Model Admins): a count of entities of a type, or the sum of a number attribute,
        with one filter"""
        return _write(lambda c: kpis.add_definition(c, model_id, g.user, body))


@blp.route("/models/<uuid:model_id>/kpis/definitions/<uuid:kpi>")
class KpiDefinition(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, body, model_id, kpi):
        """Change one of the model's own KPIs (Model Admins); the values kept so far stay as they were"""
        return _write(lambda c: kpis.update_definition(c, model_id, g.user, str(kpi), body))


@blp.route("/models/<uuid:model_id>/kpis/definitions/<uuid:kpi>/delete")
class KpiDefinitionDelete(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, model_id, kpi):
        """Stop keeping one of the model's own KPIs (Model Admins); its trend so far stays in the snapshots"""
        return _write(lambda c: kpis.delete_definition(c, model_id, g.user, str(kpi)))


@blp.route("/models/<uuid:model_id>/report-designer")
class Designer(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model_id):
        """What the report designer offers for the model, its saved designs and its OData feed address"""
        def go(c):
            out = rd.choices(c, model_id)
            out["designs"] = rd.list_designs(c, model_id)["designs"]
            out["odata_url"] = od.feed_url(get_settings().public_base_url, str(model_id))
            return out
        return _read(go)


@blp.route("/models/<uuid:model_id>/report-designs")
class Designs(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, body, model_id):
        """Keep a report design {name, spec: {entity_type, columns, related: [{relationship_type, direction, other_type,
        columns}], filters: [{field, op, value}]}}; open_url opens it in Superset's chart builder"""
        return _write(lambda c: rd.create(c, model_id, g.user, body))


@blp.route("/models/<uuid:model_id>/report-designs/preview")
class DesignPreview(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, body, model_id):
        """The first rows a design gives now and its SQL, without keeping it"""
        return _write(lambda c: rd.preview(c, model_id, body))


@blp.route("/models/<uuid:model_id>/report-designs/<uuid:design>")
class Design(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, body, model_id, design):
        """Change a report design (whoever made it, or a Model Admin)"""
        return _write(lambda c: rd.update(c, model_id, g.user, str(design), body))


@blp.route("/models/<uuid:model_id>/report-designs/<uuid:design>/delete")
class DesignDelete(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, model_id, design):
        """Delete a report design (whoever made it, or a Model Admin)"""
        return _write(lambda c: rd.delete(c, model_id, g.user, str(design)))


# ---------------------------------------------------------------- the OData feed (a plain blueprint: OData's own JSON)
odata_blp = FlaskBlueprint("odata", __name__, url_prefix="/api/v1/odata")
HEADERS = {"OData-Version": "4.0"}


def _base(model_id) -> str:
    return od.feed_url(get_settings().public_base_url, str(model_id))


def _odata(fn):
    try:
        with get_engine().connect() as conn:
            return fn(conn)
    except repo.NotFound as exc:
        return _error(404, str(exc))
    except EditError as exc:
        return _error(getattr(exc, "status", 400), str(exc))


def _error(status: int, message: str):
    r = jsonify({"error": {"code": str(status), "message": message}})
    r.status_code = status
    r.headers.update(HEADERS)
    return r


@odata_blp.after_request
def _challenge(response):
    """Excel and Power BI ask for a user name and password when told Basic sign-in is possible."""
    if response.status_code == 401:
        response.headers["WWW-Authenticate"] = 'Basic realm="EA Explorer", charset="UTF-8"'
    response.headers.setdefault("OData-Version", "4.0")
    return response


@odata_blp.route("/models/<uuid:model_id>/", methods=["GET"])
@signed_in
def service(model_id):
    def go(c):
        r = jsonify(od.service_document(c, model_id, _base(model_id)))
        r.headers.update(HEADERS)
        return r
    return _odata(go)


@odata_blp.route("/models/<uuid:model_id>/$metadata", methods=["GET"])
@signed_in
def metadata(model_id):
    return _odata(lambda c: Response(od.metadata(c, model_id), mimetype="application/xml", headers=HEADERS))


@odata_blp.route("/models/<uuid:model_id>/<table>", methods=["GET"])
@signed_in
def table(model_id, table):
    def go(c):
        r = jsonify(od.query(c, model_id, table, dict(request.args), _base(model_id)))
        r.headers.update(HEADERS)
        return r
    return _odata(go)
