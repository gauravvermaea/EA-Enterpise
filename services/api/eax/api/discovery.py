"""Data discovery and ingestion (the Release 3 epic, D670): import sources that are OData feeds EA Explorer reads,
endpoints other systems push to, or documents read by the AI engine; each run becomes a delivery to review.

POST   /models/<m>/discovery-sources              add one {name, kind odata|push|ai, url, auth_ref, schedule, mapping}
PATCH  /discovery-sources/<s>                     change it (the mapping a person confirmed, the schedule, ...)
DELETE /discovery-sources/<s>                     delete it (refused while a delivery of it waits; past deliveries stay)
GET    /discovery-sources/<s>                     it, its last run and the matches to confirm
POST   /discovery-sources/<s>/look                read it now: its sets, fields, keys and links, the mapping suggested
POST   /discovery-sources/<s>/run {full}          run it now: what changed becomes a delivery (previewed in the background)
POST   /discovery-sources/<s>/matches {entity_type, found, entity}   the found item is that element (or new: no entity)
POST   /import-sources/<s>/push                   a system sends {"<set>": [records]}: the same, as a delivery; signed in
                                                  with a token or, as the OData feed, a user name and password (Basic)
GET    /discovery-sources/<s>/kit                 a push source's Python kit as a zip (script, requirements, README, samples)
GET    /discovery-sources/<s>/kit/code            the same to show and copy on the Discovery tab
GET    /admin/ai-engine    PUT /admin/ai-engine   the AI engine for discovery {mode off|cloud|local, url, model, key_ref}

Anyone who may change the model's content sets up and runs its discovery; a delivery is accepted by a Committer, Model
Sub Admin or Model Admin, as every delivery (D465). The AI engine is chosen by a Super Admin; off until then."""

from __future__ import annotations

from functools import wraps

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint

from .. import deliveries as dv
from .. import discovery as dc
from .. import discovery_kit as kit
from .. import odata_auth
from ..auth import _test_lock, require_auth
from ..config import get_settings
from .deliveries import _preview
from .models import Free, FreeIn
from .sheets import _read, _write

blp = Blueprint("discovery", __name__, url_prefix="/api/v1",
                description="Data discovery and ingestion: OData feeds read, pushes taken, documents read by AI (R3 epic)")
SECURITY = [{"bearerAuth": []}]


def basic_or_token(view):
    """require_auth, or a user name and password (HTTP Basic) as the OData feed takes them (D433): what a script sends
    with requests' auth=(user, password) (the Python kit, D674). A personal token or API key works as the password."""
    with_token = require_auth()(view)

    def locked(*args, **kwargs):
        _test_lock(g.user)                   # a self-test in progress refuses a normal person's changes (R2.51)
        return view(*args, **kwargs)
    with_basic = odata_auth.signed_in(locked)

    @wraps(view)
    def wrapper(*args, **kwargs):
        if request.headers.get("Authorization", "").lower().startswith("basic "):
            return with_basic(*args, **kwargs)
        return with_token(*args, **kwargs)
    return wrapper


def _model(source_id) -> str:
    return _read(lambda c: str(dv._source(c, source_id)["model_guid"]))


def _with_preview(out: dict, model) -> dict:
    if out.get("load"):
        out["task"] = _preview(out["load"], model)
    return out


@blp.route("/models/<uuid:model_id>/discovery-sources")
class Sources(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(201, Free)
    @require_auth()
    def post(self, data, model_id):
        """Adds a discovery source {name, kind (odata, push or ai), url, auth_ref (the name of a setting holding the
        sign-in, never the secret), schedule (off, daily, weekly), mapping, values_win}"""
        return _write(lambda c: dc.setup(c, g.user, model_id, data or {}), "discovery_source.added", model_id,
                      {"name": (data or {}).get("name"), "kind": (data or {}).get("kind")})


@blp.route("/discovery-sources/<source_id>")
class Source(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, source_id):
        """The discovery source: its kind, address, schedule, mapping, last run and the matches waiting to be confirmed"""
        def read(c):
            src = dv._source(c, source_id)
            dc._may_write(c, g.user, dc.repo.get_model(c, str(src["model_guid"])))
            return dc.describe(c, src)
        return _read(read)

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def patch(self, data, source_id):
        """Changes it {kind, url, auth_ref, schedule, mapping, values_win, active}"""
        model = _model(source_id)
        return _write(lambda c: dc.setup(c, g.user, model, {**dc.describe(c, dv._source(c, source_id)), **(data or {})}, source_id),
                      "discovery_source.changed", model, {"source": source_id})

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def delete(self, source_id):
        """Deletes the source: refused while a delivery of it waits for review; what it delivered stays in Loads and the
        model; what it saw and the matches confirmed go with it"""
        model = _model(source_id)
        return _write(lambda c: dc.remove(c, g.user, source_id), "discovery_source.deleted", model, {"source": source_id})


@blp.route("/discovery-sources/<source_id>/look")
class Look(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, source_id):
        """Reads the source now and says what is in it (sets, fields, keys, links) with the mapping suggested; changes
        nothing"""
        return _read(lambda c: dc.look(c, g.user, source_id))


@blp.route("/discovery-sources/<source_id>/run")
class Run(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(202, Free)
    @require_auth()
    def post(self, data, source_id):
        """Runs it now {full}: what is new or changed since the last delivery becomes a delivery (previewed in the
        background, then accepted or declined); the found names that may be elements already are listed to confirm"""
        model = _model(source_id)
        out = _write(lambda c: dc.run(c, g.user, source_id, full=bool((data or {}).get("full"))), "discovery_source.run",
                     model, {"source": source_id})
        return _with_preview(out, model)


@blp.route("/discovery-sources/<source_id>/matches")
class Matches(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def post(self, data, source_id):
        """A person's answer to a suggested match {entity_type, found, entity}: the element (its id) or new (no entity)"""
        d = data or {}
        model = _model(source_id)
        return _write(lambda c: dc.decide(c, g.user, source_id, str(d.get("entity_type") or ""), str(d.get("found") or ""),
                                          d.get("entity") or None), "discovery_match.decided", model,
                      {"source": source_id, "found": d.get("found")})


@blp.route("/import-sources/<source_id>/push")
class Push(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(202, Free)
    @basic_or_token
    def post(self, source_id):
        """A system sends what it has, as JSON {"<set>": [records]} or {"value": [records], "set": "<set>"}: what is new or
        changed becomes a delivery to review. The source's service account, or anyone who may load into the model, with a
        token or a user name and password (Basic)"""
        payload = request.get_json(silent=True)
        model = _model(source_id)
        out = _write(lambda c: dc.push(c, g.user, source_id, payload if payload is not None else {}), "discovery_source.push",
                     model, {"source": source_id})
        return _with_preview(out, model)


@blp.route("/discovery-sources/<source_id>/kit")
class Kit(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, source_id):
        """A push source's Python kit as a zip: push_to_eax.py, requirements.txt, a README (a venv, the command with this
        source's address) and sample CSV files made from the model's metamodel"""
        name, data = _read(lambda c: kit.kit(c, g.user, source_id, get_settings().public_base_url))
        return Response(data, mimetype="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@blp.route("/discovery-sources/<source_id>/kit/code")
class KitCode(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, source_id):
        """The kit's script, requirements, command and samples, to show and copy on the Discovery tab"""
        return _read(lambda c: kit.code(c, g.user, source_id, get_settings().public_base_url))


@blp.route("/admin/ai-engine")
class AiEngine(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth("settings.manage")
    def get(self):
        """The AI engine discovery uses: off, cloud (the organisation's own key, named by a setting) or local (Super Admins)"""
        return _read(dc.ai_settings)

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("settings.manage")
    def put(self, data):
        """Chooses it {mode, url (its chat-completions interface), model, key_ref}: Super Admins"""
        return _write(lambda c: dc.save_ai_settings(c, g.user, data or {}), "ai_engine.changed", None,
                      {"mode": (data or {}).get("mode")})
