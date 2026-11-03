"""Who am I: the signed-in user as the API sees them."""

from flask import g
from flask.views import MethodView
from flask_smorest import Blueprint

from ..auth import require_auth
from .schemas import Me

blp = Blueprint("me", __name__, url_prefix="/api/v1/me", description="The signed-in user")


@blp.route("")
class MeView(MethodView):
    @blp.response(200, Me)
    @blp.doc(security=[{"bearerAuth": []}])
    @require_auth()
    def get(self):
        """The signed-in user and their roles"""
        u = g.user
        return {"username": u.username, "email": u.email, "name": u.name, "roles": u.roles}
