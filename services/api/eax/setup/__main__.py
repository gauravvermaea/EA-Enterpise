"""Run by the "setup" service before everything else:  python -m eax.setup

1. Checks the config file for missing values and unchanged example passwords.
2. Creates a self-signed TLS certificate if the TLS folder has none.
3. Renders the Keycloak realm (users, roles, clients) for Keycloak to import.
4. Builds the Superset sample dashboard bundle (phase 0 demo).

It is safe to run on every start.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from string import Template

from ..config import public_url
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
    "EAX_SUPERSET_OIDC_SECRET", "EAX_MAYAN_OIDC_SECRET",
]


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
    weak = [k for k, v in os.environ.items() if k.startswith("EAX_") and v.startswith("change-me")]
    if weak:
        message = "still set to the example value: " + ", ".join(sorted(weak))
        if env("EAX_DEPLOYMENT", "laptop") == "laptop":
            warnings.append(message + " (allowed on a laptop only)")
        else:
            problems.append(message)
    dev = [k for k, v in os.environ.items() if k.startswith("EAX_") and v == DEV_PASSWORD]
    if dev and env("EAX_DEPLOYMENT", "laptop") != "laptop":
        problems.append("still set to the development password: " + ", ".join(sorted(dev)))
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
    json.loads(text)  # fail early if the result is not valid JSON
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
        ("Mayan broker (Valkey)", "(none)", v("EAX_DMS_BROKER_PASSWORD")),
        ("MCP server (dev token)", "(bearer)", v("EAX_MCP_DEV_TOKEN")),
    ]
    print("EA Explorer setup: DEVELOPMENT LOGINS (laptop only - never use these on a server)")
    for account, user, password in rows:
        print(f"  {account:<30} {user:<12} {password}")


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
    print_logins(values)
    print(f"EA Explorer setup: done. Open {values['EAX_PUBLIC_URL']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
