"""The sign-in check for IT and Super Admins (owner, 6 Nov 2026, D215).

When an IT Admin or Super Admin signs in, the screens ask for this check; it runs in the job runner, in the background,
and when anything needs the admin's attention it makes one notification for that admin, needing action, listing every
problem, with a link to Administration > Services. It looks at:
  * containers: a container that should run is stopped or exited with an error, Docker says unhealthy, it ran out of
    memory (red); it is still starting, it restarted, or it is above 90% of its memory limit (amber);
  * the health checks of every service: down (red); a warning or slower than a second (amber);
  * backups (none, or older than set on Administration > Backups) and the site certificate (expired: red; within 30 days: amber);
  * config and versions: API and database versions differ, the operations helper cannot be reached (red), a laptop
    default password or token still set on a server (red; the setting names only, never the values);
  * file systems: Docker's disk, the work folder or the backups folder above 80% full (amber) or 90% (red).
The admin's previous open sign-in notification is resolved when the new check runs, so only the latest is open. The
webhooks hear it only when the list of problems has changed since the last one, so every sign-in does not repeat it.
"""

from __future__ import annotations

import logging
import os
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

log = logging.getLogger(__name__)

KIND = "system.health"
LINK = "#/admin/system"
LAPTOP_SECRET = "P^55w0rd1234&"
LAPTOP_DEFAULTS = {"EAX_OPS_TOKEN": "eax-ops-laptop"}
SECRET_WORDS = ("PASSWORD", "TOKEN", "SECRET")
ONE_SHOT = {"setup", "reports-init"}     # set-up containers that run once and stop


def health_now() -> dict:
    """Every service's health check and every container's state and use, read afresh (Administration > Services)."""
    from . import health as hc
    from .api.admin import _ops_raw
    checks = {"api": hc.check_api, "db": hc.check_database, "keycloak": hc.check_keycloak, "web": hc.check_web,
              "proxy": hc.check_proxy, "reports": hc.check_reports, "documents": hc.check_dms,
              "documents_broker": hc.check_dms_broker, "drawio": hc.check_drawio, "mcp": hc.check_mcp,
              "backups": hc.check_backup, "library": hc.check_library, "views": hc.check_views, "api_jobs": hc.check_jobs,
              "operations": hc.check_operations, "personal": hc.check_personal}
    with ThreadPoolExecutor(max_workers=len(checks) + 1) as pool:
        futures = {k: pool.submit(f) for k, f in checks.items()}

        def ops_stats():
            started = time.perf_counter()
            try:
                return _ops_raw("GET", "/stats?fresh=1", timeout=60), round((time.perf_counter() - started) * 1000), None
            except Exception as exc:  # noqa: BLE001
                return None, round((time.perf_counter() - started) * 1000), str(exc)
        st = pool.submit(ops_stats)
        out = {"checks": {k: f.result() for k, f in futures.items()}}
        stats, ms, err = st.result()
    out["checks"]["ops"] = {"name": "Operations helper", "status": "down" if err else "up", "response_ms": ms,
                            "detail": err or "answering"}
    out["containers"] = (stats or {}).get("containers", [])
    out["volumes_at"] = (stats or {}).get("volumes_at")
    out["filesystems"] = (stats or {}).get("filesystems", [])        # owner, 8 Nov 2026: the disks too
    out["docker_disk"] = (stats or {}).get("docker_disk", [])
    out["problems"] = (stats or {}).get("problems", [])
    out["checked_at"] = time.time()
    if err:
        out["helper"] = f"The operations helper is not reachable, so the containers cannot be read ({err})."
    return out


def _should_run() -> dict[str, bool]:
    """Container name -> whether it should be running (core: always; optional: when its service is switched on)."""
    from . import services
    want: dict[str, bool] = {}
    for s in services.describe_core():
        for c in s["containers"]:
            want[c] = True
    for s in services.describe():
        for c in s["containers"]:
            want[c] = want.get(c, False) or bool(s["on"])
    return want


def certificate_days(host: str = "", port: int = 443) -> float | None:
    """Days until the site certificate (what the proxy presents) expires; None when it cannot be read."""
    from cryptography import x509
    host = host or os.environ.get("EAX_PROXY_HOST", "proxy")
    try:
        pem = ssl.get_server_certificate((host, port), timeout=5)
    except (OSError, ssl.SSLError):
        return None
    cert = x509.load_pem_x509_certificate(pem.encode())
    return (cert.not_valid_after_utc - datetime.now(UTC)).total_seconds() / 86400


def default_secrets(env: dict[str, str] | None = None) -> list[str]:
    """Names of the passwords and tokens that still have the laptop's default value."""
    env = os.environ if env is None else env
    names = [k for k, v in env.items() if k.startswith("EAX_") and any(w in k for w in SECRET_WORDS) and v == LAPTOP_SECRET]
    names += [k for k, v in LAPTOP_DEFAULTS.items() if env.get(k) == v]
    return sorted(set(names))


def find_problems(h: dict, *, want: dict[str, bool] | None = None, cert_days: float | None = None,
                  versions: tuple[str | None, str] | None = None, deployment: str = "laptop",
                  env: dict[str, str] | None = None) -> list[dict]:
    """Everything that needs an admin's attention: [{level: red|amber, area, text}], red first."""
    want = want if want is not None else {}
    out: list[dict] = []

    def add(level: str, area: str, text_: str) -> None:
        out.append({"level": level, "area": area, "text": text_})

    for c in h.get("containers", []):
        name, state = c.get("service", "?"), c.get("state")
        if name in ONE_SHOT:
            if state == "exited" and c.get("exit_code"):
                add("red", "Containers", f"{name} (set-up) ended with exit code {c['exit_code']}")
            continue
        if c.get("oom_killed"):
            add("red", "Containers", f"{name} was stopped for running out of memory")
        if state != "running":
            if want.get(name, True):
                code = f", exit code {c['exit_code']}" if c.get("exit_code") else ""
                add("red", "Containers", f"{name} is {state}{code} but should be running")
            continue
        if c.get("health") == "unhealthy":
            add("red", "Containers", f"{name}: Docker says unhealthy")
        elif c.get("health") == "starting":
            add("amber", "Containers", f"{name} is still starting")
        if (c.get("restarts") or 0) > 0:
            add("amber", "Containers", f"{name} restarted {c['restarts']} time{'s' if c['restarts'] != 1 else ''}")
        if (c.get("memory_percent") or 0) > 90:
            add("amber", "Containers", f"{name} uses {c['memory_percent']:.0f}% of its memory limit")
    for key, c in (h.get("checks") or {}).items():
        if c.get("status") == "off":
            continue
        if key == "ops" and c.get("status") == "down":
            add("red", "Config and versions", f"The operations helper cannot be reached: {c.get('detail')}")
        elif key == "backups":
            if c.get("status") in ("warning", "down"):
                add("amber" if c["status"] == "warning" else "red", "Backups", str(c.get("detail")))
        elif c.get("status") == "down":
            add("red", "Services", f"{c.get('name', key)} is down: {c.get('detail')}")
        elif c.get("status") == "warning":
            add("amber", "Services", f"{c.get('name', key)}: {c.get('detail')}")
        elif (c.get("response_ms") or 0) > 1000:
            add("amber", "Services", f"{c.get('name', key)} answered slowly ({c['response_ms']} ms)")
    for p in h.get("problems") or []:
        add("amber", "Containers", f"The operations helper could not read everything: {p}")
    if cert_days is not None:
        if cert_days < 0:
            add("red", "Certificates", f"The site certificate expired {abs(cert_days):.0f} days ago")
        elif cert_days < 30:
            add("amber", "Certificates", f"The site certificate expires in {cert_days:.0f} days")
    if versions and versions[0] and versions[0] != versions[1]:
        add("red", "Config and versions", f"The database is at version {versions[0]} but the API is {versions[1]}: run the upgrade")
    if deployment != "laptop":
        names = default_secrets(env)
        if names:
            add("red", "Config and versions", f"Laptop default passwords or tokens are still set on this {deployment}: {', '.join(names)}")
    for fs in h.get("filesystems") or []:          # the disks (owner, 8 Nov 2026): over 80% used amber, over 90% red
        if fs.get("same_as") or fs.get("error"):
            continue
        if fs.get("level") in ("red", "amber"):
            add(fs["level"], "File systems", f"{fs['label']} is {fs['used_percent']:.0f}% full ({fs['free_bytes'] / 1e9:.1f} GB free)")
    out.sort(key=lambda p: (p["level"] != "red", p["area"]))
    return out


def _db_version(conn) -> str | None:
    try:
        from .versioning import database_version
        return database_version(conn)
    except Exception:  # noqa: BLE001
        return None


def run(username: str, conn=None) -> int | None:
    """The check for one admin who has just signed in; the notification's id, or None when all is well."""
    from . import __version__
    from .config import get_settings
    from .db import get_engine
    h = health_now()
    try:
        want = _should_run()
    except Exception:  # noqa: BLE001
        want = {}
    try:
        days = certificate_days()
    except Exception:  # noqa: BLE001
        days = None
    if conn is not None:
        return _notify(conn, username, h, want, days, get_settings().deployment, __version__)
    with get_engine().begin() as c:
        return _notify(c, username, h, want, days, get_settings().deployment, __version__)


def _notify(conn, username: str, h: dict, want: dict, days, deployment: str, api_version: str) -> int | None:
    from . import notify
    user = (username or "").lower()
    problems = find_problems(h, want=want, cert_days=days, versions=(_db_version(conn), api_version),
                             deployment=deployment)
    from . import personal as P
    try:
        P.run(conn, """
            UPDATE personal.notifications n SET resolved_at = now(), resolved_by = 'system',
                   resolution = 'A newer sign-in check replaced it'
             WHERE n.kind = :k AND n.needs_action AND n.resolved_at IS NULL
               AND EXISTS (SELECT 1 FROM personal.notification_recipients r WHERE r.notification_id = n.id AND r.username = :u)""",
              k=KIND, u=user)
    except P.Unavailable:
        pass
    if not problems:
        return None
    red = sum(1 for p in problems if p["level"] == "red")
    title = (f"{red} problem{'s' if red != 1 else ''} and {len(problems) - red} warning{'s' if len(problems) - red != 1 else ''} "
             "need your attention" if red else f"{len(problems)} warning{'s' if len(problems) != 1 else ''} for the administrators")
    body = "\n".join(f"{'●' if p['level'] == 'red' else '○'} {p['area']}: {p['text']}" for p in problems)
    try:
        last = (P.one(conn, "SELECT body FROM personal.notifications WHERE kind = :k ORDER BY id DESC LIMIT 1", k=KIND) or {}).get("body")
    except P.Unavailable:
        last = None
    return notify.create(conn, kind=KIND, category="system", title=title, body=body, link=LINK, actor="system",
                         recipients=[user], needs_action=True, include_actor=True, webhooks=(last != body))
