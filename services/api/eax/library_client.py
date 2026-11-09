"""The main API's side of the library service (phase 15.2, D346): a separate service with its own database, reached
inside the network at EAX_LIBRARY_URL (http://library:8100) with the library key (EAX_LIBRARY_KEY), for what only the
main API does: a project's library into and out of the project's backup, and the sample libraries on a laptop.

The library being off or down never stops a backup or a restore: they say what was left out."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE = "/api/library/v1"
TIMEOUT = 60


class LibraryDown(Exception):
    pass


def service_on() -> bool:
    return os.environ.get("EAX_SERVICE_LIBRARY", "on").strip().lower() not in ("off", "false", "0", "no", "disabled")


def _key() -> str:
    laptop = os.environ.get("EAX_DEPLOYMENT", "laptop") == "laptop"
    return os.environ.get("EAX_LIBRARY_KEY") or ("eax-library-laptop" if laptop else "")


def _call(method: str, path: str, body: dict | None = None):
    if not service_on():
        raise LibraryDown("the library service is switched off")
    url = os.environ.get("EAX_LIBRARY_URL", "http://library:8100").rstrip("/") + BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"X-Library-Key": _key(), "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - an address inside the network, from the config
            raw = r.read()
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read() or b"{}").get("message")
        except ValueError:
            msg = None
        raise LibraryDown(msg or f"the library answered {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise LibraryDown(f"the library is not answering ({exc.__class__.__name__})") from exc
    return json.loads(raw or b"null")


def export_project(project_guid: str) -> dict | None:
    """The project's library (folders, pages, links, files) or None when it has none."""
    out = _call("GET", f"/internal/projects/{project_guid}/export")
    return out or None


def import_project(project_guid: str, project_name: str, data: dict, actor: str, keep_sharing: bool = False,
                   guid_map: dict[str, str] | None = None) -> dict:
    """Into the (new or restored) project. guid_map: old guid -> new, so the pages' links to the project, its documents
    and its canvases point at the restored ones."""
    if guid_map:
        text = json.dumps(data)
        for old, new in guid_map.items():
            if old and new and old != new:
                text = text.replace(old, new)
        data = json.loads(text)
    return _call("POST", f"/internal/projects/{project_guid}/import",
                 {"project_name": project_name, "library": data, "actor": actor, "keep_sharing": keep_sharing})


def seed(data: dict) -> dict:
    return _call("POST", "/internal/seed", data)
