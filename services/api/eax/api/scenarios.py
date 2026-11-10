"""Scenario planning in a project (phase 27.1, D364, D490 to D495): what the Scenarios tab shows.

GET /projects/<p>/scenarios                      the baseline and each scenario model: figures, comparison, impact,
                                                 suggested score; the assessments kept (?baseline=<model> to choose it)
GET /projects/<p>/scenarios/<model>/compare      one scenario against the baseline in full
GET /projects/<p>/scenario-assessments/<a>       one assessment (SCN-001 or its id)
GET /projects/<p>/scenario-assessments/<a>/docx  the assessment as a Word document

Scenario models are made, what-ifs applied and assessments recorded through MCP (the prompt plan_scenarios), as the
person; the tab shows the result. Figures include the person's own uncommitted changes (their what-ifs).
"""

from __future__ import annotations

from urllib.parse import quote

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import projects as pj
from .. import repository as repo
from .. import scenarios as sc
from ..auth import require_auth
from ..metamodel_edit import EditError
from .models import Free

blp = Blueprint("scenarios", __name__, url_prefix="/api/v1", description="Scenario planning in a project (phase 27.1)")
SECURITY = [{"bearerAuth": []}]


def _run(fn):
    try:
        with pj.connections(False) as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404) if isinstance(exc, EditError) else 404, message=str(exc))


@blp.route("/projects/<string:project>/scenarios")
class Scenarios(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project):
        """The baseline and the scenario models compared with it, and the assessments recorded"""
        return _run(lambda c: sc.overview(c, project, g.user, request.args.get("baseline") or None))


@blp.route("/projects/<string:project>/scenarios/<string:model>/compare")
class ScenarioCompare(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project, model):
        """One scenario model against the baseline in full"""
        return _run(lambda c: sc.compare_one(c, project, g.user, model, request.args.get("baseline") or None))


@blp.route("/projects/<string:project>/scenario-assessments/<string:aid>")
class ScenarioAssessment(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, project, aid):
        """One scenario assessment"""
        return _run(lambda c: sc.get_assessment(c, project, g.user, aid))


@blp.route("/projects/<string:project>/scenario-assessments/<string:aid>/docx")
class ScenarioAssessmentDocx(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, project, aid):
        """The scenario assessment as a Word document"""
        data, name = _run(lambda c: sc.assessment_file(c, project, g.user, aid))
        return Response(data, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
