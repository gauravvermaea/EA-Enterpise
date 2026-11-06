"""Model icons (D247).

GET    /models/<m>/icon          the uploaded image (for an <img> fetched with the token; library icons are drawn by the screens)
PUT    /models/<m>/icon          {library: <name>} or {library: null} to remove it (Model Admins, Super Admins)
POST   /models/<m>/icon          the image as the request body (multipart file "file", or raw bytes); PNG, JPEG, WebP or SVG,
                                 up to 256 KB, for this model alone
GET    /model-icons              the library's names
"""

from __future__ import annotations

from flask import Response, g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import model_icons as mi
from .. import repository as repo
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError
from .models import Free, FreeIn

blp = Blueprint("icons", __name__, url_prefix="/api/v1", description="Model icons")
SECURITY = [{"bearerAuth": []}]


def _run(fn, write=False):
    try:
        with (get_engine().begin() if write else get_engine().connect()) as conn:
            return fn(conn)
    except (repo.NotFound, EditError) as exc:
        abort(getattr(exc, "status", 404) if isinstance(exc, EditError) else 404, message=str(exc))


@blp.route("/model-icons")
class Library(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """The built-in icon library's names, and the icon each kind of model starts with"""
        return {"library": list(mi.LIBRARY), "default_by_kind": mi.DEFAULT_BY_KIND, "max_bytes": mi.MAX_BYTES}


@blp.route("/models/<uuid:model_id>/icon")
class ModelIcon(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, model_id):
        """The model's uploaded icon image"""
        data, ct = _run(lambda c: mi.get_upload(c, model_id))
        return Response(data, mimetype=ct, headers={"Cache-Control": "private, max-age=86400",
                                                     "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
                                                     "X-Content-Type-Options": "nosniff"})

    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth()
    def put(self, data, model_id):
        """Pick a library icon {library: name}, or remove the icon {library: null}"""
        return _run(lambda c: mi.set_icon(c, model_id, g.user, library=(data or {}).get("library")), write=True)

    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def post(self, model_id):
        """Upload an icon for this model alone: a multipart file "file", or the image as the body"""
        f = request.files.get("file")
        raw = f.read(mi.MAX_BYTES + 1) if f else request.get_data(cache=False)[: mi.MAX_BYTES + 1]
        if not raw:
            abort(400, message="Send the image as a file.")
        return _run(lambda c: mi.set_icon(c, model_id, g.user, data=raw), write=True)
