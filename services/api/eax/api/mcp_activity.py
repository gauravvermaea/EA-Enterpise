"""The AI activity log (phases 26/27, D368, D482): every MCP call per person; your own, or (Super Admins and IT Admins)
everyone's. Also the OAuth remote connector's details for the MCP page (D483)."""

from __future__ import annotations

from flask import g, request
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from .. import mcp_activity as ma
from ..auth import require_auth
from ..config import get_settings
from ..db import get_engine
from .models import Free

blp = Blueprint("mcp_activity", __name__, url_prefix="/api/v1/mcp", description="The AI activity log and the MCP connector (phases 26/27)")
SECURITY = [{"bearerAuth": []}]


@blp.route("/activity")
class Activity(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """MCP calls, newest first: yours, or anyone's for Super Admins and IT Admins (who=, kind=, tool=, days=)"""
        a = request.args
        try:
            with get_engine().connect() as conn:
                return ma.listing(conn, g.user, a.get("who", ""), a.get("kind", ""), a.get("tool", ""),
                                  int(a.get("days") or 30), int(a.get("limit") or 300))
        except PermissionError as exc:
            abort(403, message=str(exc))
        except ValueError as exc:
            abort(422, message=str(exc))


@blp.route("/tools")
class McpTools(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """Every MCP tool and what it does (R2.54): area, name, description, parameters, whether it changes anything;
        read from the tools' own code"""
        from .. import mcp_catalogue
        t = mcp_catalogue.tools()
        return {"tools": t, "count": len(t)}


@blp.route("/connector")
class Connector(MethodView):
    @blp.doc(security=SECURITY)
    @blp.response(200, Free)
    @require_auth()
    def get(self):
        """What to give an AI app to add EA Explorer as a remote connector (OAuth through Keycloak, D483)"""
        s = get_settings()
        base = s.public_base_url
        return {"url": f"{base}/mcp", "resource_metadata": f"{base}/.well-known/oauth-protected-resource/mcp",
                "authorization_server": f"{base}/auth/realms/{s.realm}", "client_id": "eax-mcp",
                "registration": f"{base}/auth/realms/{s.realm}/clients-registrations/openid-connect"}
