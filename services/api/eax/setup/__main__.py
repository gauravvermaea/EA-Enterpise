"""Run by the "setup" service before everything else:  python -m eax.setup

1. Checks the config file for missing values and unchanged example passwords.
2. Creates a self-signed TLS certificate if the TLS folder has none.
3. Renders the Keycloak realm (users, roles, clients) for Keycloak to import.
4. Builds the Superset sample dashboard bundle (phase 0 demo) and the standard report bundles (phase 5).

It is safe to run on every start.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from string import Template

from .. import permissions
from ..config import public_url
from .superset_reports import build_report_bundles
from .superset_sample import build_sample_bundle
from .tls import ensure_certificate

DEPLOY = Path(os.environ.get("EAX_DEPLOY_DIR", "/deploy"))
TLS_DIR = Path(os.environ.get("EAX_TLS_OUT", "/tls"))
KC_IMPORT = Path(os.environ.get("EAX_KC_IMPORT_OUT", "/kc-import"))
RENDERED = Path(os.environ.get("EAX_RENDERED_OUT", "/rendered"))

REQUIRED = [
    "EAX_HOSTNAME", "EAX_DB_SUPERUSER_PASSWORD", "EAX_DB_PASSWORD", "EAX_DB_REPORT_PASSWORD",
    "EAX_DB_MIGRATOR_PASSWORD",
    "EAX_KEYCLOAK_DB_PASSWORD", "EAX_SUPERSET_DB_PASSWORD", "EAX_MAYAN_DB_PASSWORD",
    "EAX_DMS_BROKER_PASSWORD", "EAX_KC_ADMIN_PASSWORD", "EAX_FIRST_ADMIN_USER",
    "EAX_FIRST_ADMIN_EMAIL", "EAX_FIRST_ADMIN_PASSWORD", "EAX_SUPERSET_SECRET_KEY",
    "EAX_SUPERSET_OIDC_SECRET", "EAX_MAYAN_OIDC_SECRET", "EAX_KC_SERVICE_SECRET",
]

# Laptop only (phase 3.1): one test user per role (eax/permissions.py TEST_USERS)
TEST_USERS = permissions.TEST_USERS


# The shared development password (laptop template). Refused on any other deployment kind.
DEV_PASSWORD = "P^55w0rd1234&"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def check_config() -> list[str]:
    """Return problems; unchanged example passwords are fatal except on a laptop."""
    problems, warnings = [], []
    for key in REQUIRED:
        if not env(key):
            problems.append(f"{key} is empty")
    realm = env("EAX_KEYCLOAK_REALM", "eaexplorer")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", realm) or realm == "master":
        problems.append("EAX_KEYCLOAK_REALM must be 2 to 40 lower-case letters, digits or hyphens, start with a letter, "
                        "and not be master")
    weak = [k for k, v in os.environ.items() if k.startswith("EAX_") and v.startswith("change-me")]
    if weak:
        message = "still set to the example value: " + ", ".join(sorted(weak))
        if env("EAX_DEPLOYMENT", "laptop") == "laptop":
            warnings.append(message + " (allowed on a laptop only)")
        else:
            problems.append(message)
    if env("EAX_DEPLOYMENT", "laptop") != "laptop" and env("EAX_OPS_TOKEN", "eax-ops-laptop") in ("eax-ops-laptop", ""):
        problems.append("EAX_OPS_TOKEN is still the laptop value: set a long random value for the operations helper")
    dev = [k for k, v in os.environ.items() if k.startswith("EAX_") and v == DEV_PASSWORD]
    if dev and env("EAX_DEPLOYMENT", "laptop") != "laptop":
        problems.append("still set to the development password: " + ", ".join(sorted(dev)))
    library_on = env("EAX_SERVICE_LIBRARY", "on").lower() not in ("off", "false", "0", "no", "disabled")
    if library_on and env("EAX_DEPLOYMENT", "laptop") != "laptop":       # the library service (phase 15.2, D346)
        if not env("EAX_LIBRARY_DB_PASSWORD"):
            problems.append("EAX_LIBRARY_DB_PASSWORD is empty: the library service needs its own database password")
        if env("EAX_LIBRARY_KEY", "eax-library-laptop") in ("eax-library-laptop", ""):
            problems.append("EAX_LIBRARY_KEY is still the laptop value: set a long random value (the main API's key for the library)")
    views_on = env("EAX_SERVICE_VIEWS", "on").lower() not in ("off", "false", "0", "no", "disabled")
    if views_on and env("EAX_DEPLOYMENT", "laptop") != "laptop":         # the views service (phase 28, D405)
        if not env("EAX_VIEWS_DB_PASSWORD"):
            problems.append("EAX_VIEWS_DB_PASSWORD is empty: the views service needs its own database password")
        if env("EAX_VIEWS_KEY", "eax-views-laptop") in ("eax-views-laptop", ""):
            problems.append("EAX_VIEWS_KEY is still the laptop value: set a long random value (the main API's key for the views service)")
    temporary = env("EAX_FIRST_ADMIN_PASSWORD_TEMPORARY", "true").lower()
    if temporary not in ("true", "false"):
        problems.append("EAX_FIRST_ADMIN_PASSWORD_TEMPORARY must be true or false")
    for w in warnings:
        print(f"EA Explorer setup WARNING: {w}")
    return problems


def derived_values() -> dict[str, str]:
    host, port = env("EAX_HOSTNAME", "localhost"), env("EAX_HTTPS_PORT", "443")
    values = {k: v for k, v in os.environ.items() if k.startswith("EAX_")}
    values.update(
        EAX_KEYCLOAK_REALM=env("EAX_KEYCLOAK_REALM", "eaexplorer"),
        EAX_PUBLIC_URL=public_url(host, port),
        EAX_PUBLIC_URL_PORT=f"https://{host}:{port}",
        EAX_REPORTS_URL=public_url(host, port, "reports."),
        EAX_REPORTS_URL_PORT=f"https://reports.{host}:{port}",
        EAX_DOCS_URL=public_url(host, port, "docs."),
        EAX_DOCS_URL_PORT=f"https://docs.{host}:{port}",
    )
    return values


def render_realm(values: dict[str, str]) -> Path:
    """Fill the realm template; every value is JSON-escaped before it is placed.

    EAX_FIRST_ADMIN_PASSWORD_TEMPORARY is the exception: it is placed as a JSON boolean.
    """
    template = Template((DEPLOY / "keycloak" / "realm-eaexplorer.json.tmpl").read_text())
    escaped = {k: json.dumps(v)[1:-1] for k, v in values.items()}
    temporary = values.get("EAX_FIRST_ADMIN_PASSWORD_TEMPORARY", "true").strip().lower() != "false"
    escaped["EAX_FIRST_ADMIN_PASSWORD_TEMPORARY"] = "true" if temporary else "false"
    text = template.substitute(escaped)
    realm = json.loads(text)  # fail early if the result is not valid JSON
    # the test users: always on a laptop; on a server only when asked (EAX_TEST_USERS=on, a staging server, with its
    # own EAX_TEST_USER_PASSWORD), so the automated tests can sign in as every role (phase 36.1, D525)
    server_tests = values.get("EAX_TEST_USERS", "off").strip().lower() in ("on", "true", "yes", "1") \
        and bool(values.get("EAX_TEST_USER_PASSWORD"))
    if values.get("EAX_DEPLOYMENT", "laptop") == "laptop" or server_tests:
        password = values.get("EAX_TEST_USER_PASSWORD") or values.get("EAX_FIRST_ADMIN_PASSWORD", "")
        for username, role, _models in TEST_USERS:
            first, *rest = username.split("_")[1:]
            realm["users"].append({
                "username": username, "email": f"{username}@example.org", "emailVerified": True, "enabled": True,
                "firstName": "Test", "lastName": " ".join([first, *rest]).title(),
                "credentials": [{"type": "password", "value": password, "temporary": False}],
                "realmRoles": sorted({role, "eax-user", "offline_access", "uma_authorization"}),
            })
        text = json.dumps(realm, indent=2)
    KC_IMPORT.mkdir(parents=True, exist_ok=True)
    out = KC_IMPORT / "eaexplorer-realm.json"
    out.write_text(text)
    out.chmod(0o644)
    return out


def print_logins(values: dict[str, str]) -> None:
    """Laptop (development) only: print every user name and password to the console."""
    if values.get("EAX_DEPLOYMENT", "laptop") != "laptop":
        return
    v = lambda k, d="": values.get(k, d)  # noqa: E731
    rows = [
        ("EA Explorer (Keycloak realm)", v("EAX_FIRST_ADMIN_USER", "eaadmin"), v("EAX_FIRST_ADMIN_PASSWORD")),
        ("Keycloak administrator", v("EAX_KC_ADMIN", "kcadmin"), v("EAX_KC_ADMIN_PASSWORD")),
        ("Superset break-glass admin", "admin", v("EAX_SUPERSET_ADMIN_PASSWORD")),
        ("Mayan EDMS administrator", v("EAX_MAYAN_ADMIN_USER", "admin"), v("EAX_MAYAN_ADMIN_PASSWORD")),
        ("PostgreSQL superuser", "postgres", v("EAX_DB_SUPERUSER_PASSWORD")),
        ("PostgreSQL EA Explorer", "eax_app", v("EAX_DB_PASSWORD")),
        ("PostgreSQL reporting", "eax_report", v("EAX_DB_REPORT_PASSWORD")),
        ("PostgreSQL installer (reference models)", "eax_migrator", v("EAX_DB_MIGRATOR_PASSWORD")),
        ("PostgreSQL Keycloak", "keycloak", v("EAX_KEYCLOAK_DB_PASSWORD")),
        ("PostgreSQL Superset", "superset", v("EAX_SUPERSET_DB_PASSWORD")),
        ("PostgreSQL Mayan", "mayan", v("EAX_MAYAN_DB_PASSWORD")),
        ("PostgreSQL Library", "eax_library", v("EAX_LIBRARY_DB_PASSWORD") or v("EAX_DB_PASSWORD")),
        ("PostgreSQL Views", "eax_views", v("EAX_VIEWS_DB_PASSWORD") or v("EAX_DB_PASSWORD")),
        ("Mayan broker (Valkey)", "(none)", v("EAX_DMS_BROKER_PASSWORD")),
        ("MCP server (dev token)", "(bearer)", v("EAX_MCP_DEV_TOKEN")),
        ("Break-glass (when Keycloak is down)", "break-glass", v("EAX_BREAK_GLASS_PASSWORD")),
    ]
    test_password = v("EAX_TEST_USER_PASSWORD") or v("EAX_FIRST_ADMIN_PASSWORD")
    rows += [(f"Test user ({role.removeprefix('eax-')})", user, test_password) for user, role, _m in TEST_USERS]
    print("EA Explorer setup: DEVELOPMENT LOGINS (laptop only - never use these on a server)")
    for account, user, password in rows:
        print(f"  {account:<46} {user:<22} {password}")


def main() -> int:
    problems = check_config()
    if problems:
        for p in problems:
            print(f"EA Explorer setup ERROR: {p}", file=sys.stderr)
        print("Fix eaexplorer.env and start again.", file=sys.stderr)
        return 1

    values = derived_values()
    host = values["EAX_HOSTNAME"]
    created = ensure_certificate(TLS_DIR, host)
    print(f"EA Explorer setup: TLS certificate {'created (self-signed)' if created else 'present'}")

    realm = render_realm(values)
    print(f"EA Explorer setup: Keycloak realm rendered to {realm}")

    bundle = build_sample_bundle(
        RENDERED / "superset",
        db_password=values["EAX_DB_REPORT_PASSWORD"],
        db_name=values.get("EAX_DB_NAME", "eaexplorer"),
    )
    print(f"EA Explorer setup: Superset sample dashboard bundle written to {bundle}")
    reports = build_report_bundles(
        RENDERED / "superset",
        db_password=values["EAX_DB_REPORT_PASSWORD"],
        db_name=values.get("EAX_DB_NAME", "eaexplorer"),
        public_url=values["EAX_PUBLIC_URL"],
    )
    print(f"EA Explorer setup: {len(reports)} standard report bundles written to {RENDERED / 'superset' / 'reports'}")
    print_logins(values)
    print(f"EA Explorer setup: done. Open {values['EAX_PUBLIC_URL']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
