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
    from .api.break_glass import blp as break_glass_blp
    from .api.change_log import blp as change_log_blp
    from .api.commits import blp as commits_blp
    from .api.content import blp as content_blp
    from .api.grids import blp as grids_blp
    from .api.heartbeat import blp as heartbeat_blp
    from .api.jobs import blp as jobs_blp
    from .api.me import blp as me_blp
    from .api.metamodel import blp as metamodel_blp
    from .api.metamodel_edit import blp as metamodel_edit_blp
    from .api.models import blp as models_blp
    from .api.notifications import blp as notifications_blp
    from .api.sheets import blp as sheets_blp
    from .api.sql import blp as sql_blp
    from .api.tasks import blp as tasks_blp
    from .api.versions import blp as versions_blp
    from .api.viewpoints import blp as viewpoints_blp

    for blp in (heartbeat_blp, me_blp, access_blp, break_glass_blp, jobs_blp, audit_blp, metamodel_blp,
                metamodel_edit_blp, models_blp, content_blp, grids_blp, viewpoints_blp, commits_blp,
                versions_blp, change_log_blp, admin_blp, sql_blp, tasks_blp, sheets_blp, notifications_blp):
        api.register_blueprint(blp)

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

    @app.after_request
    def _add_request_id(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        return response

    @app.get("/api/health")
    def health():
        """Liveness check for Docker: the process is up (does not touch the database)."""
        return {"status": "ok"}

    log.info("EA Explorer API %s started (%s deployment)", __version__, settings.deployment)
    return app
