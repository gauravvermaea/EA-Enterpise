"""The main EA Explorer API, asked with the person's own token (D346): who they are and what they may do (one place for
roles), their roles in a project, and names of what links point to. Answers are kept for a minute."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .config import get_settings

TTL = 60
_cache: dict[tuple, tuple[float, object]] = {}
_lock = threading.Lock()


class Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class Person:
    username: str
    roles: list[str] = field(default_factory=list)
    permissions: dict = field(default_factory=dict)
    token: str = ""
    extra_headers: dict = field(default_factory=dict)

    @property
    def library_admin(self) -> bool:
        return "super-admin" in self.roles or bool(self.permissions.get("library.curate"))


def _get(path: str, headers: dict) -> dict:
    req = urllib.request.Request(get_settings().api_url + path, headers={**headers, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read().decode() or "{}").get("message") or exc.reason
        except Exception:  # noqa: BLE001
            msg = exc.reason
        raise Refused(exc.code, str(msg)) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise Refused(503, f"EA Explorer's API does not answer ({exc})") from None


def _cached(key: tuple, fn):
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < TTL:
            return hit[1]
    val = fn()
    with _lock:
        if len(_cache) > 2000:
            _cache.clear()
        _cache[key] = (now, val)
    return val


def whoami(headers: dict) -> Person:
    """The signed-in person, from the main API (/api/v1/me): refuses when the token is not good."""
    auth = {k: v for k, v in headers.items() if k.lower() in ("authorization", "x-as")}
    if not auth:
        raise Refused(401, "Sign in first.")
    me = _cached(("me", tuple(sorted(auth.items()))), lambda: _get("/api/v1/me", auth))
    return Person(username=me.get("username") or "", roles=list(me.get("roles") or []), permissions=dict(me.get("permissions") or {}),
                  token=auth.get("Authorization", ""), extra_headers=auth)


def library_settings(person: Person) -> dict:
    me = _cached(("me", tuple(sorted(person.extra_headers.items()))), lambda: _get("/api/v1/me", person.extra_headers))
    return dict(me.get("library") or {"mode": "ours"})


def project(person: Person, project_id: str) -> dict:
    """The project as this person sees it: its name, their roles, whether they may change it (it is read only when
    frozen). Refused (403 or 404) when they may not see it."""
    d = _cached(("project", tuple(sorted(person.extra_headers.items())), project_id),
                lambda: _get(f"/api/v1/projects/{project_id}", person.extra_headers))
    return {"id": d.get("id") or project_id, "name": d.get("name") or "", "my_roles": list(d.get("my_roles") or []),
            "may_admin": bool(d.get("may_admin")), "may_contribute": bool(d.get("may_contribute")), "frozen": bool(d.get("frozen")),
            "status": d.get("status")}
