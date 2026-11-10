"""Surveys (phase 38.1, D375, D446 to D449) and EA capability maturity (phase 40, D377, D450 to D453).

GET    /surveys                                to answer, answered, mine, and every survey for a Super Admin
POST   /surveys                                a new draft {title, description, spec, recipients, anonymous, open_link,
                                               closes_at, remind_every_days} (Super Admin, Model Creator, Library Admin)
GET    /surveys/people?q=                      who a survey can go to: people, global roles, models and projects
GET    /surveys/<s>                            one survey (its questions)
PATCH  /surveys/<s>                            change it (the questions and anonymity only while a draft)
DELETE /surveys/<s>                            delete a draft
POST   /surveys/<s>/copy                       a new draft with the same questions and recipients
POST   /surveys/<s>/send                       send a draft: the people are worked out and asked (their task list)
POST   /surveys/<s>/recipients                 add people while open {recipients}
POST   /surveys/<s>/remind                     remind everyone who has not answered
POST   /surveys/<s>/close                      close it (their open tasks are resolved)
POST   /surveys/<s>/reopen                     open it again
GET    /surveys/<s>/answer                     the survey to answer, with my saved answers
PUT    /surveys/<s>/answer                     save {answers} or send {answers, submit: true}
GET    /surveys/<s>/results                    results by question and progress (who runs it)
GET    /surveys/<s>/xlsx                       the results and every response as Excel
GET    /maturity                               every assessment, the trend and the evidence now (Super Admin)
POST   /maturity                               a new assessment {title, recipients, targets, weights, closes_at, send}
GET    /maturity/questions                     the starting questions (nine elements, six levels)
GET    /maturity/<s>                           an assessment's scores, gaps, evidence and the one before
"""

from __future__ import annotations

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from sqlalchemy.exc import DBAPIError

from .. import audit
from .. import maturity as mt
from .. import surveys as sv
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError, _db_message
from .models import Free, FreeIn

blp = Blueprint("surveys", __name__, url_prefix="/api/v1",
                description="Surveys (phase 38.1) and EA capability maturity assessments (phase 40)")
SECURITY = [{"bearerAuth": []}]


def _read(fn):
    try:
        with get_engine().begin() as conn:
            return fn(conn)
    except EditError as exc:
        abort(getattr(exc, "status", 400), message=str(exc))


def _write(fn, action: str | None = None, details=None):
    try:
        with get_engine().begin() as conn:
            out = fn(conn)
            if action:
                d = details(out) if callable(details) else (details or {})
                audit.record(conn, actor=g.user.username, action=action, object_type="survey",
                             object_id=str((out or {}).get("id") or d.get("id") or ""), details=d,
                             request_id=getattr(g, "request_id", None))
            return out
    except EditError as exc:
        abort(getattr(exc, "status", 400), message=str(exc))
    except DBAPIError as exc:
        abort(403 if "Not allowed" in str(exc.orig) else 409, message=_db_message(exc))


def _title(out) -> dict:
    return {"title": (out or {}).get("title", ""), "kind": (out or {}).get("kind", "")}


@blp.route("/surveys")
class Surveys(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Surveys to answer, answered, the ones I run (and every one for a Super Admin)"""
        return _read(lambda c: sv.listing(c, g.user))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data):
        """A new survey, as a draft"""
        return _write(lambda c: sv.create(c, g.user, data or {}), "survey.create", _title)


@blp.route("/surveys/people")
class SurveyPeople(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Who a survey can go to: people, global roles, models (with their roles) and projects"""
        if not (sv.may_create(g.user) or mt.may_manage(g.user)):
            abort(403, message="Making surveys needs the Super Admin, Model Creator or Library Admin role.")
        return _read(lambda c: sv.people_to_pick(c, request.args.get("q", "")))


@blp.route("/surveys/<string:sid>")
class Survey(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, sid):
        """One survey and its questions"""
        return _read(lambda c: sv.get(c, g.user, sid))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def patch(self, data, sid):
        """Change a survey (the questions, recipients and anonymity only while it is a draft)"""
        return _write(lambda c: sv.update(c, g.user, sid, data or {}), "survey.update", _title)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, sid):
        """Delete a draft"""
        return _write(lambda c: sv.delete(c, g.user, sid), "survey.delete", lambda o: {"id": o["deleted"]})


def _action(name: str, fn, doc: str, action: str | None = None, body: bool = False):
    """A POST /surveys/<s>/<name> doing fn(conn, user, sid[, data])."""
    def post(self, *args, sid):
        data = args[0] if body else {}
        return _write(lambda c: fn(c, g.user, sid, data) if body else fn(c, g.user, sid), action,
                      lambda o: {**_title(o), "id": sid, **({"reminded": o.get("reminded")} if "reminded" in (o or {}) else {})})
    post.__doc__ = doc
    post = require_auth()(post)
    post = blp.response(200, Free)(post)
    if body:
        post = blp.arguments(FreeIn)(post)
    post = blp.doc(security=SECURITY)(post)
    view = type(f"Survey_{name}", (MethodView,), {"post": post})
    blp.route(f"/surveys/<string:sid>/{name}")(view)


_action("copy", sv.copy, "A new draft with the same questions and recipients", "survey.copy")
_action("send", sv.send, "Send a draft: the people it is for are worked out and asked (a task in their notifications)", "survey.send")
_action("recipients", lambda c, u, s, d: sv.add_recipients(c, u, s, (d or {}).get("recipients")),
        "Ask more people while it is open (nobody is taken off)", "survey.recipients", body=True)
_action("remind", sv.remind, "Remind everyone asked who has not answered", "survey.remind")
_action("close", sv.close, "Close the survey (open tasks are resolved; a maturity assessment keeps its evidence and scores)",
        "survey.close")
_action("reopen", sv.reopen, "Open a closed survey again", "survey.reopen")


@blp.route("/surveys/<string:sid>/answer")
class SurveyAnswer(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, sid):
        """The survey to answer, with my saved answers (none kept in an anonymous survey)"""
        return _read(lambda c: sv.my_answer(c, g.user, sid))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, sid):
        """Save my answers {answers}, or send them {answers, submit: true}"""
        d = data or {}
        # who answered is logged; what they answered never is (and never in an anonymous survey)
        return _write(lambda c: sv.answer(c, g.user, sid, d.get("answers") or {}, bool(d.get("submit"))),
                      "survey.answer" if d.get("submit") else None, lambda _o: {"id": sid})


@blp.route("/surveys/<string:sid>/results")
class SurveyResults(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, sid):
        """Results by question, progress and (not anonymous) who has answered"""
        return _read(lambda c: sv.results(c, g.user, sid))


@blp.route("/surveys/<string:sid>/xlsx")
class SurveyXlsx(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, sid):
        """The results by question and every response, as an Excel workbook"""
        data, name = _read(lambda c: sv.to_xlsx(c, g.user, sid))
        return Response(data, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------- EA capability maturity (phase 40)
@blp.route("/maturity")
class Maturity(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Every maturity assessment, the trend over closed ones and the evidence EA Explorer measures now"""
        return _read(lambda c: mt.overview(c, g.user))

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data):
        """A new assessment (a draft survey with the starting questions), sent at once with send: true"""
        return _write(lambda c: mt.create(c, g.user, data or {}), "maturity.create", _title)


@blp.route("/maturity/questions")
class MaturityQuestions(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The starting questions: nine architecture elements, six levels"""
        if not mt.may_manage(g.user):
            abort(403, message="Maturity assessments are run by Super Admins.")
        return {"spec": mt.default_spec(), "levels": [{"level": i, "name": n} for i, n in mt.LEVELS],
                "elements": [{"key": k, "name": n, "about": a} for k, n, a, _d in mt.ELEMENTS]}


@blp.route("/maturity/<string:sid>")
class MaturityResult(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, sid):
        """An assessment's scores by element (mean level, target, gap, share at each level), the evidence and the one before"""
        return _read(lambda c: mt.result(c, g.user, sid))
