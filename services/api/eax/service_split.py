"""Which API a container serves (R2.27 part 2, R2.53; owner, 13 Nov 2026: "Front door routes them").

The operations service and the personal data service are containers of their own, each with its own API and health,
built from the API's code (one codebase, one image) and started with EAX_SERVE:

  EAX_SERVE=all         everything (the default: the self-test's copy of the API, unit tests, eax dev)
  EAX_SERVE=core        the main API: everything but what the services below serve
  EAX_SERVE=operations  /api/v1/operations/...  housekeeping, retention, usage, deployments, updates (port 8120)
  EAX_SERVE=personal    /api/v1/me/...          notifications, requests, favourites, saved views, skills, settings,
                                                remote instances (port 8130); /api/v1/me itself stays on the main API

The front door (deploy/proxy) sends each prefix straight to its service, with the same sign-in token; the main API no
longer answers them. Each service reads its own schema through its own connection string (eax/databases.py, D630) and
the repository's through the repository's, for who the person is and the names of what they refer to.
"""

from __future__ import annotations

import os

SERVICES: dict[str, dict] = {
    "operations": {"port": 8120, "prefix": "/api/v1/operations", "upstream": "EAX_OPERATIONS_UPSTREAM",
                   "blueprints": ("operations", "deploys", "updates"),
                   "what": "the running of the installation: housekeeping, retention, usage, deployments, updates"},
    "personal": {"port": 8130, "prefix": "/api/v1/me", "upstream": "EAX_PERSONAL_UPSTREAM",
                 "blueprints": ("personal",),
                 "what": "each person's notifications, requests, favourites, saved views, skills and settings"},
}
ALWAYS = ("health",)          # every container answers its own health


def serving() -> str:
    v = os.environ.get("EAX_SERVE", "all").strip().lower() or "all"
    return v if v in ("all", "core", *SERVICES) else "all"


def wanted(blueprint: str, role: str | None = None) -> bool:
    """Whether this container registers the blueprint."""
    role = role or serving()
    if blueprint in ALWAYS or role == "all":
        return True
    owner = next((k for k, s in SERVICES.items() if blueprint in s["blueprints"]), None)
    return owner == role if role in SERVICES else owner is None


def internal_url(path: str) -> str:
    """The container that serves this path inside the stack: its service, else the main API."""
    for key, s in SERVICES.items():
        if path.startswith(s["prefix"] + "/"):        # /api/v1/me itself (who am I) stays on the main API
            return os.environ.get(f"EAX_{key.upper()}_INTERNAL_URL", f"http://{key}:{s['port']}")
    return os.environ.get("EAX_API_INTERNAL_URL", "http://api:8000")


def route(base: str, path: str) -> str:
    """The self-test calls the main API's container directly (not the front door): a path a service serves goes to
    that service's container instead. Any other base (the front door, an outside test bench's site) is left as it is,
    as the front door routes it."""
    mains = {"http://api:8000", os.environ.get("EAX_API_INTERNAL_URL", "").rstrip("/")} - {""}
    return internal_url(path) if base.rstrip("/") in mains else base


def _migrated() -> bool:
    """The database is at the migrations' head (the main API's container runs them; a service waits)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text

    from .db import get_engine
    heads = set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
    with get_engine().connect() as c:
        have = {r[0] for r in c.execute(text("SELECT version_num FROM alembic_version")).all()}
    return heads <= have


def main(argv: list[str]) -> int:
    """python -m eax.service_split ready: waits (up to EAX_SERVICE_WAIT seconds, 15 minutes by default) until the main
    API's container has brought the database to the migrations' head, so a service never runs on old tables."""
    import time
    if argv[:1] != ["ready"]:
        print("usage: python -m eax.service_split ready")
        return 2
    end = time.time() + int(os.environ.get("EAX_SERVICE_WAIT", "900"))
    while True:
        try:
            if _migrated():
                print(f"EA Explorer {serving()} service: the database is ready")
                return 0
            why = "the migrations are not done yet"
        except Exception as exc:  # noqa: BLE001 - not there yet
            why = str(exc).splitlines()[0][:120]
        if time.time() > end:
            print(f"EA Explorer {serving()} service: gave up waiting ({why})")
            return 1
        print(f"EA Explorer {serving()} service: waiting for the database ({why})")
        time.sleep(5)


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
