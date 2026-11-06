"""Model icons (D247): a model's icon is one of the built-in library (drawn for EA Explorer; the shapes are in
services/web/src/modelIcons.js) or an image uploaded for that model alone (PNG, JPEG, WebP or SVG, up to 256 KB).
Model Admins of the model (and Super Admins) set it."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError

LIBRARY = ("building", "bank", "shield", "umbrella", "heart", "hospital", "car", "truck", "plane", "ship", "factory", "leaf", "globe", "cloud", "server", "database", "chart", "people", "briefcase", "cart", "house", "school", "bolt", "drop", "gear", "rocket", "star", "pin", "phone", "lock", "coins", "compass", "layers", "puzzle", "flag", "target", "network")
DEFAULT_BY_KIND = {"template": "layers", "reference": "bank", "project": "building"}
MAX_BYTES = 256 * 1024
TYPES = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}
UNSAFE_SVG = re.compile(r"<\s*script|\bon[a-z]+\s*=|javascript:|<\s*foreignObject|<\s*iframe|<\s*embed|<\s*object|"
                        r"xlink:href\s*=\s*[\"'](?!#)|\bhref\s*=\s*[\"'](?!#)", re.I)


def _may_set(conn, user, m: dict) -> bool:
    return perms.SUPER_ADMIN in user.roles or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"])


def sniff(data: bytes) -> str:
    """The image's type from its bytes (never from the name a browser gave it); refuses anything else."""
    for ct, magic in TYPES.items():
        if data.startswith(magic):
            return ct
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:2048].lstrip().lower()
    if head.startswith((b"<svg", b"<?xml")) and b"<svg" in data[:4096].lower():
        try:
            body = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EditError("The SVG is not UTF-8 text.") from exc
        if UNSAFE_SVG.search(body):
            raise EditError("The SVG has scripts, event handlers or links to elsewhere: draw it without them.")
        return "image/svg+xml"
    raise EditError("The icon must be a PNG, JPEG, WebP or SVG image.")


def set_icon(conn, model: Any, user, library: str | None = None, data: bytes | None = None) -> dict:
    """Sets a model's icon: a library name, or an uploaded image for that model alone; neither removes it."""
    from . import audit
    m = repo.get_model(conn, model)
    if not _may_set(conn, user, m):
        raise EditError(f"Changing {m['name']}'s icon needs the Model Admin role on it (or Super Admin).", 403)
    if library:
        library = str(library).removeprefix("lib:")
        if library not in LIBRARY:
            raise EditError(f"No icon {library!r} in the library.")
        conn.execute(text("""INSERT INTO core.model_icons (model_id, library, set_by) VALUES (:m, :l, :u)
                             ON CONFLICT (model_id) DO UPDATE SET library = EXCLUDED.library, content_type = NULL, data = NULL,
                                 set_by = EXCLUDED.set_by, set_at = now()"""), {"m": m["_id"], "l": library, "u": user.username})
        what = f"library icon {library}"
    elif data:
        if len(data) > MAX_BYTES:
            raise EditError(f"The icon is {len(data) // 1024} KB; it may be up to 256 KB.")
        ct = sniff(data)
        conn.execute(text("""INSERT INTO core.model_icons (model_id, content_type, data, set_by) VALUES (:m, :c, :d, :u)
                             ON CONFLICT (model_id) DO UPDATE SET library = NULL, content_type = EXCLUDED.content_type,
                                 data = EXCLUDED.data, set_by = EXCLUDED.set_by, set_at = now()"""),
                     {"m": m["_id"], "c": ct, "d": data, "u": user.username})
        what = f"uploaded icon ({ct}, {len(data)} bytes)"
    else:
        conn.execute(text("DELETE FROM core.model_icons WHERE model_id = :m"), {"m": m["_id"]})
        what = "no icon"
    audit.record(conn, actor=user.username, action="model.icon", object_type="model", object_id=str(m["id"]),
                 details={"icon": what})
    return {"model": str(m["id"]), "icon": what}


def get_upload(conn, model: Any) -> tuple[bytes, str]:
    m = repo.get_model(conn, model)          # only people who may read the model
    r = conn.execute(text("SELECT content_type, data FROM core.model_icons WHERE model_id = :m AND data IS NOT NULL"),
                     {"m": m["_id"]}).mappings().first()
    if not r:
        raise EditError("This model has no uploaded icon.", 404)
    return bytes(r["data"]), r["content_type"]
