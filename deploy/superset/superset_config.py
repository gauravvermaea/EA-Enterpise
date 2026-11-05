"""Superset settings for EA Explorer. Every value comes from eaexplorer.env.

Sign-in: through Keycloak (OIDC). Users are created on first sign-in and their Superset role
follows their Keycloak realm roles (AUTH_ROLES_MAPPING, re-checked at every sign-in).
Break-glass: set EAX_SUPERSET_AUTH=db in eaexplorer.env to sign in with the local admin.
"""

import os
from urllib.parse import quote

from flask_appbuilder.security.manager import AUTH_DB, AUTH_OAUTH
from superset.security import SupersetSecurityManager


def env(name, default=""):
    return os.environ.get(name, default).strip()


HOST = env("EAX_HOSTNAME", "localhost")
PORT = env("EAX_HTTPS_PORT", "443")
PUBLIC = f"https://{HOST}" if PORT == "443" else f"https://{HOST}:{PORT}"
REALM = "eaexplorer"
KC_PUBLIC = f"{PUBLIC}/auth/realms/{REALM}/protocol/openid-connect"
KC_INTERNAL = f"http://keycloak:8080/auth/realms/{REALM}/protocol/openid-connect"

# ---- Core
SECRET_KEY = env("EAX_SUPERSET_SECRET_KEY")
SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://superset:{quote(env('EAX_SUPERSET_DB_PASSWORD'), safe='')}@db:5432/superset"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False

# ---- Behind the nginx proxy, over HTTPS
ENABLE_PROXY_FIX = True
PROXY_FIX_CONFIG = {"x_for": 1, "x_proto": 1, "x_host": 1, "x_port": 1, "x_prefix": 1}
PREFERRED_URL_SCHEME = "https"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
TALISMAN_ENABLED = False  # headers are set by the proxy

# ---- Caches in Superset's own PostgreSQL database (no Valkey/Redis)
# SupersetMetastoreCache keeps cached values in the metadata database, so nothing is lost on restart
# and no separate cache service is needed.
_db_cache = {"CACHE_TYPE": "SupersetMetastoreCache", "CACHE_DEFAULT_TIMEOUT": 300}
CACHE_CONFIG = {**_db_cache, "CACHE_KEY_PREFIX": "superset_"}
DATA_CACHE_CONFIG = {**_db_cache, "CACHE_KEY_PREFIX": "superset_data_"}
FILTER_STATE_CACHE_CONFIG = {**_db_cache, "CACHE_KEY_PREFIX": "superset_filter_", "CACHE_DEFAULT_TIMEOUT": 86400}
EXPLORE_FORM_DATA_CACHE_CONFIG = {**_db_cache, "CACHE_KEY_PREFIX": "superset_explore_", "CACHE_DEFAULT_TIMEOUT": 86400}

# ---- Sign-in through Keycloak
AUTH_TYPE = AUTH_DB if env("EAX_SUPERSET_AUTH") == "db" else AUTH_OAUTH
AUTH_USER_REGISTRATION = True
AUTH_USER_REGISTRATION_ROLE = "Gamma"
AUTH_ROLES_SYNC_AT_LOGIN = True
READER = "EA Explorer reports"   # may read the report datasets, for the models they have (eax_reports_init.py, D138)
AUTH_ROLES_MAPPING = {
    # Keycloak's global roles (phase 3.1). Only the Super Admin is a Superset Admin; IT Admins and
    # Keycloak Admins see no content (D98). Everyone else reads the reports of the models they have.
    "eax-super-admin": ["Admin"],
    "eax-it-admin": ["Gamma"],
    "eax-keycloak-admin": ["Gamma"],
    "eax-user-admin": ["Gamma", READER],
    "eax-model-creator": ["Gamma", READER],
    "eax-library-admin": ["Gamma", READER],
    "eax-user": ["Gamma", READER],
}
OAUTH_PROVIDERS = [
    {
        "name": "keycloak",
        "icon": "fa-key",
        "token_key": "access_token",
        "remote_app": {
            "client_id": "superset",
            "client_secret": env("EAX_SUPERSET_OIDC_SECRET"),
            "client_kwargs": {"scope": "openid email profile"},
            # The browser goes to the public address; Superset talks to Keycloak internally.
            "authorize_url": f"{KC_PUBLIC}/auth",
            "access_token_url": f"{KC_INTERNAL}/token",
            "api_base_url": f"{KC_INTERNAL}/",
            "jwks_uri": f"{KC_INTERNAL}/certs",
        },
    }
]


class KeycloakSecurityManager(SupersetSecurityManager):
    """Reads the user and their realm roles from Keycloak's userinfo endpoint."""

    def oauth_user_info(self, provider, response=None):
        if provider != "keycloak":
            return super().oauth_user_info(provider, response)
        data = self.appbuilder.sm.oauth_remotes[provider].get("userinfo").json()
        return {
            "username": data.get("preferred_username", ""),
            "first_name": data.get("given_name", ""),
            "last_name": data.get("family_name", ""),
            "email": data.get("email", ""),
            "role_keys": data.get("roles", []),
        }


CUSTOM_SECURITY_MANAGER = KeycloakSecurityManager


def FLASK_APP_MUTATOR(app):  # noqa: N802 - the name Superset looks for
    """After a clean restart the browser can still hold a session cookie for a person the new Superset does not
    have; Flask-AppBuilder's user loader then fails with a 500 error on every page. Wrap the loader so such a
    cookie counts as signed out, and the person simply signs in again through Keycloak."""
    lm = getattr(app, "login_manager", None)
    loader = getattr(lm, "_user_callback", None)
    if loader is None:
        return

    def safe_loader(user_id):
        try:
            return loader(user_id)
        except (AttributeError, TypeError, ValueError):
            return None

    lm._user_callback = safe_loader

# ---- Features
# ENABLE_TEMPLATE_PROCESSING: model access uses {{ current_username() }} (D138)
FEATURE_FLAGS = {"DASHBOARD_RBAC": True, "EMBEDDED_SUPERSET": False, "ENABLE_TEMPLATE_PROCESSING": True}
# links in report tables (Open in EA Explorer)
HTML_SANITIZATION = True
SQLLAB_CTAS_NO_LIMIT = True
