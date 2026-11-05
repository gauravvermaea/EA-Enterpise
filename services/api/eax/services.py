"""Optional services: switched on or off in the config file, with the eax command or from the administration console
(owner, 5 Nov 2026, D191). Every one is on unless the config file says off.

    EAX_SERVICE_REPORTS     reports (Apache Superset: containers reports-init and reports)
    EAX_SERVICE_DOCUMENTS   documents (Mayan EDMS: containers dms-broker and dms)
    EAX_SERVICE_DRAWIO      diagrams (the draw.io container)
    EAX_SERVICE_MCP         the MCP server inside the api container
    EAX_SERVICE_CHANGE_LOG  the change log shipper inside the api container (no new entries while off)
    EAX_SERVICE_BACKUPS     the backup container

The core never switches off: the database, Keycloak, the API, the web screens, the proxy and the operations helper.

The config file is the one source of truth. The eax command and the operations helper copy its switches (no secrets)
into work/services.env, which the api container reads at /eax-work/services.env (the config file itself may not be
readable there: on Linux it is private to its owner). So a switch made in the console is known at once, without
recreating the container. Without that file (tests, the command line) the environment is read.

    python -m eax.services is-on mcp     exit code 0 when on (the api container's entrypoint)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

WORK = Path(os.environ.get("EAX_WORK_MOUNT", "/eax-work"))
FILES = [WORK / "services.env", WORK / "eaexplorer.env"]

# key: (setting, name, what it is, containers in start order, what is hidden or stops while off)
SERVICES: dict[str, tuple[str, str, str, list[str], str]] = {
    "reports": ("EAX_SERVICE_REPORTS", "Reports", "Apache Superset", ["reports-init", "reports"],
                "The Reports tab, report links and dashboards."),
    "documents": ("EAX_SERVICE_DOCUMENTS", "Documents", "Mayan EDMS", ["dms-broker", "dms"],
                  "The document links and the documents tile."),
    "drawio": ("EAX_SERVICE_DRAWIO", "Diagrams", "draw.io", ["drawio"], "The draw.io editor (/drawio/)."),
    "mcp": ("EAX_SERVICE_MCP", "MCP server", "inside the API", ["api"],
            "Language models can no longer connect at /mcp; the MCP page says it is off."),
    "change_log": ("EAX_SERVICE_CHANGE_LOG", "Change log", "inside the API", ["api"],
                   "No new change log entries while off; the ones already there stay and can be read."),
    "backups": ("EAX_SERVICE_BACKUPS", "Backups", "the backup container", ["backup"],
                "No backups are taken; eax backup and restore say the service is off."),
}
OFF = {"off", "false", "0", "no", "disabled"}

# the core: always on, never switched off; shown beside the optional ones (restart only)
CORE: dict[str, tuple[str, str, list[str], str]] = {
    "web": ("Web screens", "nginx serving the React app", ["web"], "The screens you are using."),
    "api": ("API", "Flask", ["api"], "Every screen, report and the MCP server read and write through it."),
    "keycloak": ("Sign-in", "Keycloak", ["keycloak"], "Sign-in, people and their roles."),
    "db": ("Database", "PostgreSQL", ["db"], "The repository: models, history, settings."),
    "proxy": ("Proxy", "nginx", ["proxy"], "The one address everything is reached through (HTTPS)."),
    "ops": ("Operations helper", "inside Docker", ["ops"], "Restarts and switches services for this console."),
}


def _file_values() -> dict[str, str]:
    lines: list[str] = []
    for f in FILES:
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
            break
        except OSError:
            continue
    out = {}
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("'\"")
    return out


def raw(key: str) -> str:
    setting = SERVICES[key][0]
    file = _file_values()
    if setting in file:
        return file[setting]
    if key == "mcp" and "EAX_MCP_ENABLED" in file:            # the name before phase 10
        return file["EAX_MCP_ENABLED"]
    return os.environ.get(setting, os.environ.get("EAX_MCP_ENABLED", "on") if key == "mcp" else "on")


def enabled(key: str) -> bool:
    return raw(key).strip().lower() not in OFF


def switches() -> dict[str, bool]:
    return {k: enabled(k) for k in SERVICES}


def describe() -> list[dict]:
    return [{"key": k, "setting": s[0], "name": s[1], "product": s[2], "containers": s[3], "when_off": s[4], "on": enabled(k)}
            for k, s in SERVICES.items()]


def describe_core() -> list[dict]:
    return [{"key": k, "name": c[0], "product": c[1], "containers": c[2], "about": c[3], "on": True, "core": True}
            for k, c in CORE.items()]


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "is-on" and sys.argv[2] in SERVICES:
        sys.exit(0 if enabled(sys.argv[2]) else 1)
    print("usage: python -m eax.services is-on " + "|".join(SERVICES))
    sys.exit(2)
