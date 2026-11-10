"""The main API's side of the views service (phases 28 and 29, D405): a separate service with its own database
(eaxviews), reached inside the network at EAX_VIEWS_URL (http://views:8110) with the views key (EAX_VIEWS_KEY), for what
only the main API does with a model's views: a tag holds their versions, a copied or child model gets copies bound to its
own entities, a merge brings across the views the target lacks, a model package or backup carries them, a deleted
model's views go with it, MCP reads and makes them, and the sample views on a laptop.

The people's own calls (list, open, save, versions, the model's own views) go from the screens to /api/views/v1
directly. The views service being off or down never stops a tag, a copy, a merge or a package: they say what was left out."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "/api/views/v1"
TIMEOUT = 60


class ViewsDown(Exception):
    def __init__(self, message: str, status: int = 503, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.details = details or {}


def service_on() -> bool:
    return os.environ.get("EAX_SERVICE_VIEWS", "on").strip().lower() not in ("off", "false", "0", "no", "disabled")


def _key() -> str:
    laptop = os.environ.get("EAX_DEPLOYMENT", "laptop") == "laptop"
    return os.environ.get("EAX_VIEWS_KEY") or ("eax-views-laptop" if laptop else "")


def _call(method: str, path: str, body: dict | None = None, query: dict | None = None):
    if not service_on():
        raise ViewsDown("the views service is switched off")
    url = os.environ.get("EAX_VIEWS_URL", "http://views:8110").rstrip("/") + BASE + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    data = json.dumps(body, default=str).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"X-Views-Key": _key(), "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - an address inside the network, from the config
            raw = r.read()
    except urllib.error.HTTPError as exc:
        try:
            got = json.loads(exc.read() or b"{}")
        except ValueError:
            got = {}
        raise ViewsDown(got.get("message") or f"the views service answered {exc.code}", exc.code, got.get("errors") or {}) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ViewsDown(f"the views service is not answering ({exc.__class__.__name__})") from exc
    return json.loads(raw or b"null")


def _m(model: Any) -> str:
    return urllib.parse.quote(str(model), safe="")


def list_views(model: Any, marker: Any = None) -> dict:
    return _call("GET", f"/internal/models/{_m(model)}/drawn-views", query={"marker": marker})


def get_view(model: Any, view: Any, version: int | None = None, with_xml: bool = True, marker: Any = None) -> dict:
    return _call("GET", f"/internal/models/{_m(model)}/drawn-views/{_m(view)}",
                 query={"version": version, "xml": "1" if with_xml else "0", "marker": marker})


def create(model: Any, data: dict, actor: str, marker: Any = None) -> dict:
    """A view made by the main API (MCP, the sample data): its objects were checked here already."""
    return _call("POST", f"/internal/models/{_m(model)}/drawn-views", {**data, "actor": actor, "marker": marker})


def save(model: Any, view: Any, data: dict, actor: str, marker: Any = None) -> dict:
    return _call("PUT", f"/internal/models/{_m(model)}/drawn-views/{_m(view)}", {**data, "actor": actor, "marker": marker})


def hold_for_tag(model: Any, tag: Any) -> list[dict]:
    return (_call("POST", f"/internal/models/{_m(model)}/tags/{_m(tag)}") or {}).get("drawn_views") or []


def tag_view(model: Any, tag: Any, view: Any) -> dict:
    return _call("GET", f"/internal/models/{_m(model)}/tags/{_m(tag)}/drawn-views/{_m(view)}")


def export_model(model: Any, all_versions: bool = True) -> dict:
    return _call("GET", f"/internal/models/{_m(model)}/export", query={"all": "1" if all_versions else "0"}) or {}


def import_model(model: Any, views: dict, actor: str, ent_map: dict | None = None, rel_map: dict | None = None,
                 only_new: bool = False, source: str = "package", latest_only: bool = False, replace: bool = False) -> dict:
    return _call("POST", f"/internal/models/{_m(model)}/import", {"views": views, "actor": actor, "ent_map": ent_map or {},
                                                                  "rel_map": rel_map or {}, "only_new": only_new, "source": source,
                                                                  "latest_only": latest_only, "replace": replace})


def copy_model(src: Any, dst: Any, actor: str, ent_map: dict, rel_map: dict, only_new: bool = False, source: str = "model-copy") -> dict:
    return _call("POST", f"/internal/models/{_m(src)}/copy-to/{_m(dst)}", {"actor": actor, "ent_map": ent_map, "rel_map": rel_map,
                                                                          "only_new": only_new, "source": source})


def delete_model(model: Any, actor: str) -> dict:
    return _call("DELETE", f"/internal/models/{_m(model)}", {"actor": actor})
