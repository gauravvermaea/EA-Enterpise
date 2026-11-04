"""Read the audit log (system administrators only)."""

from flask.views import MethodView
from flask_smorest import Blueprint
from sqlalchemy import text

from ..auth import require_auth
from ..db import get_engine
from .schemas import AuditEvent, AuditQuery

blp = Blueprint("audit", __name__, url_prefix="/api/v1/audit", description="Audit log")


@blp.route("")
class AuditList(MethodView):
    @blp.arguments(AuditQuery, location="query")
    @blp.response(200, AuditEvent(many=True))
    @blp.doc(security=[{"bearerAuth": []}])
    @require_auth("system.operate")
    def get(self, args):
        """Latest audit events (system administrators)"""
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, at, actor, action, object_type, object_id, source, details "
                    "FROM audit.events ORDER BY id DESC LIMIT :limit"
                ),
                {"limit": args["limit"]},
            ).mappings().all()
        return [dict(r) for r in rows]
