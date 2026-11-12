"""Flask application factory."""

from __future__ import annotations

import logging
import uuid

from flask import Flask, g, request
from flask_smorest import Api

from . import __version__
from .config import get_settings
from .logging_setup import configure_logging

log = logging.getLogger(__name__)


def create_app(testing: bool = False) -> Flask:
    configure_logging()
    settings = get_settings()

    app = Flask(__name__)
    app.config.update(
        TESTING=testing,
        API_TITLE="EA Explorer API",
        API_VERSION=__version__,
        OPENAPI_VERSION="3.0.3",
        OPENAPI_URL_PREFIX="/api",
        OPENAPI_JSON_PATH="openapi.json",
        OPENAPI_SWAGGER_UI_PATH="/docs",
        OPENAPI_SWAGGER_UI_URL="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/",
        API_SPEC_OPTIONS={
            "info": {
                "description": (
                    "EA Explorer REST API. Public calls: heartbeat and health. Everything else "
                    "needs a Keycloak access token: sign in on the start page, or use "
                    "'Authorize' with a token."
                ),
            },
            "servers": [{"url": settings.public_base_url, "description": "This installation"}],
        },
        JSON_SORT_KEYS=False,
    )

    api = Api(app)
    api.spec.components.security_scheme(
        "bearerAuth", {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    )

    from .api.access import blp as access_blp
    from .api.admin import blp as admin_blp
    from .api.audit import blp as audit_blp
    from .api.backups import blp as backups_blp
    from .api.break_glass import blp as break_glass_blp
    from .api.change_log import blp as change_log_blp
    from .api.commits import blp as commits_blp
    from .api.commons import blp as commons_blp
    from .api.content import blp as content_blp
    from .api.drawn_views import blp as drawn_views_blp
    from .api.grids import blp as grids_blp
    from .api.heartbeat import blp as heartbeat_blp
    from .api.icons import blp as icons_blp
    from .api.jobs import blp as jobs_blp
    from .api.kpi_reports import blp as kpi_reports_blp
    from .api.kpi_reports import odata_blp
    from .api.me import blp as me_blp
    from .api.metamodel import blp as metamodel_blp
    from .api.metamodel_edit import blp as metamodel_edit_blp
    from .api.model_wizards import blp as model_wizards_blp
    from .api.models import blp as models_blp
    from .api.notifications import blp as notifications_blp
    from .api.projects import blp as projects_blp
    from .api.quality import blp as quality_blp
    from .api.sheets import blp as sheets_blp
    from .api.sql import blp as sql_blp
    from .api.startup import blp as startup_blp
    from .api.tasks import blp as tasks_blp
    from .api.trees import blp as trees_blp
    from .api.versions import blp as versions_blp
    from .api.views import blp as views_blp

    for blp in (heartbeat_blp, me_blp, access_blp, break_glass_blp, jobs_blp, audit_blp, metamodel_blp,
                metamodel_edit_blp, models_blp, content_blp, grids_blp, views_blp, commits_blp,
                versions_blp, change_log_blp, admin_blp, sql_blp, tasks_blp, sheets_blp, notifications_blp, backups_blp,
                quality_blp, icons_blp, trees_blp, startup_blp, projects_blp, model_wizards_blp, commons_blp, drawn_views_blp, kpi_reports_blp):
        api.register_blueprint(blp)
    # machine access and operations (phases 25 and 35, F3 of batch 1)
    from .api.machine_access import blp as machine_access_blp
    from .api.operations import blp as operations_blp
    api.register_blueprint(machine_access_blp)
    api.register_blueprint(operations_blp)
    # merging a child into its parent, dedupe, sample documents (phases 19, 20, 21, 15.3; F1 of batch 1)
    from .api.merge_back import blp as merge_back_blp
    api.register_blueprint(merge_back_blp)
    # surveys and EA capability maturity (phases 38.1 and 40, F4 of batch 1)
    from .api.surveys import blp as surveys_blp
    api.register_blueprint(surveys_blp)
    # the AI activity log and the MCP connector (phases 26/27, D482, D483)
    from .api.mcp_activity import blp as mcp_activity_blp
    api.register_blueprint(mcp_activity_blp)
    # scenario planning (phase 27.1, D490 to D495)
    from .api.scenarios import blp as scenarios_blp
    api.register_blueprint(scenarios_blp)
    # published import formats, deliveries and a model from a metamodel workbook (phase 34, D419, D462 to D468)
    from .api.deliveries import blp as deliveries_blp
    api.register_blueprint(deliveries_blp)
    # updating to a new release (phase 36, D417)
    from .api.updates import blp as updates_blp
    api.register_blueprint(updates_blp)
    # the outside test bench's door into a self-test run (D580, D581)
    from .api.testbench_api import blp as testbench_blp
    api.register_blueprint(testbench_blp)
    # deploying EA Explorer to another place from System admin > Deploy (phase 36, D555)
    from .api.deploys import blp as deploys_blp
    api.register_blueprint(deploys_blp)
    # eax commands from a web page: the Command centre and the Console (D554)
    from .api.command_centre import blp as command_centre_blp
    api.register_blueprint(command_centre_blp)
    from .api.banner import blp as banner_blp
    api.register_blueprint(banner_blp)
    # the documents of this version, for everyone (D550)
    from .api.documentation import blp as documentation_blp
    api.register_blueprint(documentation_blp)
    # the industry packs' files in Documents: the library's Pack tab (phase 39, D546 to D549)
    from .api.industry_packs import blp as industry_packs_blp
    api.register_blueprint(industry_packs_blp)
    from .api.platform_tests import (
        blp as platform_tests_blp,  # test runs (36.1) and scaling rules (36.3)
    )
    api.register_blueprint(platform_tests_blp)
    from .api.selftest_session import (
        blp as selftest_session_blp,  # the self-test's browser sign-in (D529)
    )
    api.register_blueprint(selftest_session_blp)
    api.spec.components.security_scheme("apiKey", {"type": "apiKey", "in": "header", "name": "X-API-Key"})
    try:   # the OData feed's Basic sign-in takes a token or API key as the password (phase 24, D433)
        from . import machine_access as _ma
        from . import odata_auth as _oa
        if _ma.odata_check not in _oa.CHECKS:
            _oa.CHECKS.append(_ma.odata_check)
    except ImportError:
        pass
    app.register_blueprint(odata_blp)          # OData's own JSON, outside the OpenAPI document (phase 24, D433)

    @app.before_request
    def _request_id() -> None:
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex

    @app.before_request
    def _log_level():
        """The log level set in the administration console (D191), applied at once."""
        from . import settings as app_settings
        app_settings.apply_log_level()

    @app.before_request
    def _upload_limit():
        """The largest upload set in the administration console (phase 10, D183), applied at once."""
        size = request.content_length or 0
        if size > 1024 * 1024 and request.method in ("POST", "PUT", "PATCH"):
            from . import settings as app_settings
            limit = int(app_settings.values().get("upload_max_mb") or 50)
            if size > limit * 1024 * 1024:
                return {"message": f"The upload is {size / 1048576:.1f} MB; the largest allowed is {limit} MB "
                                   "(Administration > System settings)."}, 413
        return None

    @app.before_request
    def _parts():
        """A part switched off in System settings (D329): its API answers 404 with why; its data is kept."""
        if not request.path.startswith("/api/v1/"):
            return None
        from . import settings as app_settings
        try:
            part = app_settings.part_of_path(request.path, app_settings.parts())
        except Exception:  # noqa: BLE001 - the database not there yet: nothing is refused for this
            return None
        if part:
            return {"message": f"{part.title()} is switched off in this installation (System admin > System settings). "
                               "Its data is kept and comes back when a Super Admin switches it on.", "part_off": part}, 404
        return None

    @app.before_request
    def _maintenance():
        """While a backup is restored (D216) the installation is read only: every change is refused with why."""
        if request.method in ("GET", "HEAD", "OPTIONS") or request.path.startswith("/api/v1/internal/"):
            return None
        from . import maintenance
        m = maintenance.state()
        if m:
            return {"message": f"EA Explorer is read only while {m.get('what') or 'a restore runs'} (started by {m.get('by') or '?'} "
                               f"at {m.get('since') or '?'}): nothing can be changed until it is done.", "maintenance": m}, 503
        return None

    @app.after_request
    def _machine_and_usage(response):
        """Phase 25: a machine credential's last use and the call in the change log; phase 35: the call counted."""
        machine = getattr(g, "machine", None)
        user = getattr(g, "user", None)
        try:
            from . import operations
            if user is not None:
                operations.count_call(user.username, request.path, machine is not None)
            if machine is not None:
                from . import machine_access
                from .db import get_engine
                with get_engine().begin() as conn:
                    machine_access.note_use(conn, machine, request.method, request.path, response.status_code,
                                            request.headers.get("X-Real-IP") or request.remote_addr or "",
                                            getattr(g, "request_id", None))
        except Exception:  # noqa: BLE001 - recording never fails the call
            log.exception("recording the call failed")
        return response

    @app.get("/api/metrics")
    def metrics():
        """Prometheus metrics (phase 35, D371): read with a token or API key that may read Administration."""
        from flask import Response

        from . import operations
        from .auth import require_auth
        from .db import get_engine

        @require_auth("system.operate")
        def read():
            operations.flush()
            with get_engine().connect() as conn:
                return Response(operations.metrics(conn), mimetype="text/plain; version=0.0.4")
        return read()

    @app.after_request
    def _add_request_id(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        return response

    @app.get("/api/health")
    def health():
        """Liveness check for Docker: the process is up (does not touch the database)."""
        return {"status": "ok"}

    @app.get("/api/startup")
    def startup_public():
        """The start-up status without signing in (D255): each part up, starting, down or off; nothing more."""
        from .api.startup import public
        try:
            return public()
        except Exception as exc:  # noqa: BLE001 - the database may not be there yet
            return {"overall": "starting", "parts": [], "message": str(exc)[:200]}

    log.info("EA Explorer API %s started (%s deployment)", __version__, settings.deployment)
    @app.errorhandler(Exception)
    def _server_error(exc):
        """A server error answers as JSON with its kind and the request's id, and its traceback goes to the API's log
        under that id: so the self-test's report (and anyone asked to look) can find it (R2.0.1: the laptop's full run
        had two bare "Internal Server Error" pages and nothing to go on). An HTTP error (abort) is answered as usual."""
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return exc
        rid = getattr(g, "request_id", "") or ""
        log.exception("server error %s on %s %s (request %s)", type(exc).__name__, request.method, request.path, rid)
        return {"code": 500, "status": "Internal Server Error", "error": type(exc).__name__, "request_id": rid,
                "message": f"A server error ({type(exc).__name__}). The API's log has the details under request {rid}."}, 500

    return app
