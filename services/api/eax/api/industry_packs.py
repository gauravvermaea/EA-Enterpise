"""The industry packs' files (phase 39; owner 10 Nov 2026, D546 to D549): the library's Pack tab.

GET  /industry-packs                          every industry: how many files its pack has in Documents
GET  /industry-packs/<industry>               one pack's tiles (book, workbook, metamodel Excel, templates, PowerPoints...)
GET  /models/<model>/industry-pack            the pack of a library reference model (its tiles), or none
GET  /industry-packs/files/<file>/download    one file (anyone signed in: the library is everyone's)
POST /industry-packs/load                     {folder: "shipped" | "extra", dry_run}: load a folder of packs into Documents
                                              (Library Admins and Super Admins; also `eax packs load` and at start-up)
"""

from __future__ import annotations

from urllib.parse import quote

from flask import Response, g
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import industry_packs as ip
from ..auth import require_auth
from ..db import get_engine
from ..metamodel_edit import EditError
from .models import Free, FreeIn

blp = Blueprint("industry_packs", __name__, url_prefix="/api/v1", description="The industry packs' files (phase 39)")
SECURITY = [{"bearerAuth": []}]


def _run(fn, write: bool = False):
    from .. import mayan
    try:
        with (get_engine().begin() if write else get_engine().connect()) as conn:
            return fn(conn)
    except EditError as exc:
        abort(getattr(exc, "status", 400), message=str(exc))
    except mayan.MayanError as exc:
        abort(exc.status, message=str(exc))


@blp.route("/industry-packs")
class Packs(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free(many=True))
    @require_auth()
    def get(self):
        """Every industry and how many files its pack has"""
        return _run(ip.listing)


@blp.route("/industry-packs/<string:industry>")
class Pack(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, industry):
        """One industry pack's tiles"""
        return _run(lambda c: ip.pack(c, industry))


@blp.route("/models/<string:model>/industry-pack")
class ModelPack(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self, model):
        """The pack of a library reference model, or none"""
        return _run(lambda c: ip.for_model(c, model))


@blp.route("/industry-packs/files/<string:file_id>/download")
class PackFile(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, file_id):
        """Download one pack file"""
        content, ctype, name = _run(lambda c: ip.download(c, file_id))
        return Response(content, mimetype=ctype or "application/octet-stream",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@blp.route("/industry-packs/load")
class Load(MethodView):
    @blp.doc(security=SECURITY)
    @blp.arguments(FreeIn)
    @blp.response(200, Free)
    @require_auth("library.curate")
    def post(self, data):
        """Load a folder of packs into Documents: the shipped packs or the extra folder (EAX_PACKS_DIR)"""
        where = (data or {}).get("folder") or "shipped"
        if where not in ("shipped", "extra"):
            abort(400, message="folder is 'shipped' (library/industry-packs) or 'extra' (the folder EAX_PACKS_DIR mounts).")
        root = ip.PACKS_DIR if where == "shipped" else ip.EXTRA_DIR
        return _run(lambda c: ip.load_folder(c, root, g.user.username, dry_run=bool((data or {}).get("dry_run"))), write=True)
