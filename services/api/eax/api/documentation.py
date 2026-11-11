"""EA Explorer's own documentation for every signed-in user (owner, 10 Nov 2026, D550): the documents of the version
that runs, from the user menu's Documentation page.

GET  /documentation                       the list, grouped, with the version
GET  /documentation/search?q=             documents holding every word, with a snippet
GET  /documentation/<key>                 one document as safe HTML
GET  /documentation/<key>/download        the document's own file (.md or .txt)
"""

from __future__ import annotations

from flask import Response, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import shipped_docs as D
from ..auth import require_auth
from .models import Free

blp = Blueprint("documentation", __name__, url_prefix="/api/v1/documentation",
                description="EA Explorer's own documentation, for every signed-in user (D550)")
SECURITY = [{"bearerAuth": []}]


@blp.route("")
class DocList(MethodView):
    @blp.response(200, Free)
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self):
        """Every document that ships with this version, grouped"""
        return D.listing()


@blp.route("/search")
class DocSearch(MethodView):
    @blp.response(200, Free)
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self):
        """Documents holding every word of q, best first, with a snippet"""
        q = request.args.get("q", "")
        return {"q": q, "results": D.search(q)}


@blp.route("/<string:key>")
class DocOne(MethodView):
    @blp.response(200, Free)
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, key):
        """One document as HTML (escaped first, so nothing in it runs)"""
        try:
            return D.document(key)
        except LookupError as exc:
            abort(404, message=str(exc))


@blp.route("/<string:key>/download")
class DocDownload(MethodView):
    @blp.doc(security=SECURITY)
    @require_auth()
    def get(self, key):
        """The document's own file"""
        try:
            name, data = D.raw(key)
        except LookupError as exc:
            abort(404, message=str(exc))
        ctype = "text/markdown; charset=utf-8" if name.endswith(".md") else "text/plain; charset=utf-8"
        return Response(data, mimetype=ctype.split(";")[0], headers={"Content-Type": ctype,
                                                                       "Content-Disposition": f'attachment; filename="{name}"'})
