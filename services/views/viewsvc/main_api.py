"""The main EA Explorer API, asked with the person's own token (D405): who they are (kept for a minute), what they may
do with a model's views (asked each time: it carries the model's last change, for "the model changed since"), and
whether a view's objects are the model's own entities (D354: checked on every save)."""

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



def _get(path: str, headers: dict, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(get_settings().api_url + path, data=data, method="POST" if body is not None else "GET",
                                 headers={**headers, "Accept": "application/json", "Content-Type": "application/json"})
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


def model_access(person: Person, model: str) -> dict:
    """The model as this person sees it: {id, name, may_draw, read_only_reason, marker}. Refused (403 or 404) when they
    may not read it. Not kept: the marker is the model's last content change."""
    return _get(f"/api/v1/models/{model}/drawn-views/access", person.extra_headers)


def check(person: Person, model: str, entities: list[str], relationships: list[str]) -> dict:
    """The main API checks a view holds only the model's own entities and relationships (D354); refused (400) when not.
    Returns the counts of missing and deleted entities."""
    return _get(f"/api/v1/models/{model}/drawn-views/check", person.extra_headers,
                {"entities": entities, "relationships": relationships})
