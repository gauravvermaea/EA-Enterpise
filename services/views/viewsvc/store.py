"""A model's views, kept in the views service's database (phases 28 and 29; owner, 10 Nov 2026, D405 to D407).

* Drawn views: draw.io files; each save a version; the last save wins, with a warning when someone saved since you
  opened it (409 unless force, D404). The objects on a view are the model's own entities: the main API checks that on
  every save (the check is passed in: main_api.check, or nothing for the main API's own trusted calls).
* Versions kept: every one, or the last EAX_VIEWS_KEEP_VERSIONS of each view; never one a model's tag holds.
* A model's own generated views (D406): definitions copied from the organisation's standard views and changed for the
  model; the picture is drawn from the model each time it is opened, never stored here.
* For the main API only: a tag holds the views' versions; a copied or child model gets copies bound to its own entities;
  a merge brings across the views the target lacks; a model package carries them; a deleted model's views go with it.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from typing import Any

from . import drawio
from .config import get_settings
from .db import one, rows
from .drawio import Refused

SOURCES = ("new", "copy", "generated", "mcp", "model-copy", "merge", "package")
VIEW_FIELDS = ("name", "category", "purpose", "concerns", "stakeholders", "element_types", "relationship_types", "heat_attribute")


def _ts(v: Any) -> str | None:
    return v.isoformat() if hasattr(v, "isoformat") else (None if v is None else str(v))


def _when(v: Any) -> dt.datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.UTC)
    w = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    return w if w.tzinfo else w.replace(tzinfo=dt.UTC)


def _changed(ver: dict | None, marker: Any) -> bool:
    """The model changed since this version was saved (D354 banner)."""
    now = _when(marker)
    if not ver or not now:
        return False
    saved = _when(ver.get("model_marker"))
    return saved is None or now > saved


# ---------------------------------------------------------------- drawn views

def _view(conn, model: str, view: Any) -> dict:
    by = "guid::text = %(v)s" if drawio.is_guid(view) else "lower(name) = lower(%(v)s)"
    v = one(conn, f"SELECT * FROM views.drawn_views WHERE model_guid::text = %(m)s AND NOT is_deleted AND {by}", m=str(model), v=str(view))
    if not v:
        raise Refused(f"No drawn view {view!r} in this model.", 404)
    return v


def _latest(conn, view_id: int) -> dict | None:
    return one(conn, "SELECT * FROM views.drawn_view_versions WHERE view_id = %(v)s ORDER BY version_no DESC LIMIT 1", v=view_id)


def _version(conn, view_id: int, n: int) -> dict | None:
    return one(conn, "SELECT * FROM views.drawn_view_versions WHERE view_id = %(v)s AND version_no = %(n)s", v=view_id, n=n)


def _row_out(v: dict, ver: dict | None, marker: Any) -> dict:
    return {"id": str(v["guid"]), "name": v["name"], "description": v["description"], "source": v["source"],
            "source_note": v["source_note"], "created_by": v["created_by"], "created_at": _ts(v["created_at"]),
            "modified_by": v["modified_by"], "modified_at": _ts(v["modified_at"]),
            "version": ver["version_no"] if ver else 0, "saved_by": ver["saved_by"] if ver else None,
            "saved_at": _ts(ver["saved_at"]) if ver else None, "model_changed_since": _changed(ver, marker)}


def list_views(conn, model: str, marker: Any = None) -> dict:
    out = []
    for v in rows(conn, "SELECT * FROM views.drawn_views WHERE model_guid::text = %(m)s AND NOT is_deleted ORDER BY lower(name)", m=str(model)):
        ver = _latest(conn, v["id"])
        try:
            parsed = drawio.parse(ver["xml"]) if ver else None
        except Refused:
            parsed = None
        out.append({**_row_out(v, ver, marker), "objects": len(parsed["objects"]) if parsed else 0,
                    "placeholders": parsed["placeholders"] if parsed else 0})
    return {"model": str(model), "views": out}


def get_view(conn, model: str, view: Any, version: int | None = None, with_xml: bool = True, marker: Any = None) -> dict:
    v = _view(conn, model, view)
    ver = _version(conn, v["id"], version) if version else _latest(conn, v["id"])
    if version and not ver:
        raise Refused(f"{v['name']} has no version {version}.", 404)
    out = _row_out(v, ver, marker)
    if ver:
        out["summary"] = drawio.summary(drawio.parse(ver["xml"]))
        if with_xml:
            out["xml"] = ver["xml"]
    out["latest_version"] = (_latest(conn, v["id"]) or {}).get("version_no", 0)
    return out


def versions(conn, model: str, view: Any) -> dict:
    v = _view(conn, model, view)
    held = {r["version_no"] for r in rows(conn, "SELECT DISTINCT version_no FROM views.tag_holds WHERE view_id = %(v)s", v=v["id"])}
    vs = rows(conn, """SELECT version_no AS version, note, saved_by, saved_at, length(xml) AS size
                         FROM views.drawn_view_versions WHERE view_id = %(v)s ORDER BY version_no DESC""", v=v["id"])
    for r in vs:
        r["saved_at"] = _ts(r["saved_at"])
        r["held_by_tag"] = r["version"] in held
    return {"id": str(v["guid"]), "name": v["name"], "versions": vs}


def _name(conn, model: str, name: str, but: int | None = None, table: str = "drawn_views") -> str:
    name = " ".join((name or "").split())[:200]
    if not name:
        raise Refused("Name the view.")
    if one(conn, f"""SELECT 1 AS x FROM views.{table} WHERE model_guid::text = %(m)s AND NOT is_deleted AND lower(name) = lower(%(n)s)
                      AND id IS DISTINCT FROM %(b)s""", m=str(model), n=name, b=but):
        raise Refused(f"This model has a {'drawn view' if table == 'drawn_views' else 'view'} called {name} already.", 409)
    return name


Check = Callable[[dict], dict] | None


def _checked(xml: str, check: Check) -> dict:
    parsed = drawio.parse(xml)
    if check:
        check(parsed)            # the main API: only the model's own entities and relationships (D354)
    return parsed


def _insert_version(conn, view_id: int, n: int, xml: str, note: str, marker: Any, actor: str) -> None:
    conn.execute("""INSERT INTO views.drawn_view_versions (view_id, version_no, xml, note, model_marker, saved_by)
                    VALUES (%(v)s, %(n)s, %(x)s, %(note)s, CAST(%(mk)s AS timestamptz), %(u)s)""",
                 {"v": view_id, "n": n, "x": xml, "note": (note or "")[:500], "mk": _ts(_when(marker)), "u": actor})


def create(conn, model: str, actor: str, data: dict, marker: Any = None, check: Check = None) -> dict:
    """A new drawn view: empty, from a draw.io file (a generated picture saved as a drawn view, MCP), or a copy of a view
    of this model (copy_from, copy_version) (D354, D407)."""
    name = _name(conn, model, data.get("name") or "")
    source, note, xml = data.get("source") or "new", data.get("source_note") or "", data.get("xml") or ""
    if data.get("copy_from"):
        src = _view(conn, model, data["copy_from"])
        ver = _version(conn, src["id"], int(data["copy_version"])) if data.get("copy_version") else _latest(conn, src["id"])
        if not ver:
            raise Refused("That view has no saved version to copy.")
        xml, source, note = ver["xml"], "copy", f"{src['name']}, version {ver['version_no']}"
    if source not in SOURCES:
        raise Refused("source is new, copy or generated.")
    xml = xml or drawio.BLANK
    _checked(xml, check)
    v = one(conn, """INSERT INTO views.drawn_views (model_guid, name, description, source, source_note, created_by, modified_by)
                     VALUES (CAST(%(m)s AS uuid), %(n)s, %(d)s, %(s)s, %(sn)s, %(u)s, %(u)s) RETURNING *""",
            m=str(model), n=name, d=(data.get("description") or "")[:2000], s=source, sn=note[:300], u=actor)
    first = {"new": "Made", "copy": f"Copied from {note}", "generated": "Made from a generated view",
             "mcp": f"Made by an AI assistant ({note})"}.get(source, data.get("note") or "Made")
    _insert_version(conn, v["id"], 1, xml, first, marker, actor)
    out = get_view(conn, model, v["guid"], marker=marker)
    out["message"] = f"Drawn view {name} made."
    return out


def save(conn, model: str, actor: str, view: Any, data: dict, marker: Any = None, check: Check = None) -> dict:
    """A new version. base_version: the version the person opened; if someone saved since: 409 with who and when, unless
    force (the last save wins, D404)."""
    v = _view(conn, model, view)
    xml = data.get("xml") or ""
    parsed = _checked(xml, check)
    latest = _latest(conn, v["id"])
    base = data.get("base_version")
    behind = latest is not None and base is not None and int(base) < latest["version_no"]
    if behind and not data.get("force"):
        raise Refused(f"{latest['saved_by']} saved this view (version {latest['version_no']}) after you opened it. "
                      "Save anyway to replace it with yours (the last save wins; theirs stays in the versions).", 409,
                      {"conflict": {"version": latest["version_no"], "saved_by": latest["saved_by"], "saved_at": _ts(latest["saved_at"])}})
    n = (latest["version_no"] if latest else 0) + 1
    _insert_version(conn, v["id"], n, xml, data.get("note") or "", marker, actor)
    conn.execute("UPDATE views.drawn_views SET modified_by = %(u)s, modified_at = now() WHERE id = %(v)s", {"u": actor, "v": v["id"]})
    dropped = prune(conn, v["id"])
    warning = f"Saved over version {latest['version_no']} by {latest['saved_by']} (kept in the versions)." if behind else None
    return {"id": str(v["guid"]), "version": n, "summary": drawio.summary(parsed), "warning": warning, "dropped_versions": dropped,
            "message": f"Saved {v['name']} as version {n}." + (f" {warning}" if warning else "")}


def prune(conn, view_id: int) -> int:
    """Only the last EAX_VIEWS_KEEP_VERSIONS versions of a view are kept (0: all); never one a tag holds, never the latest."""
    keep = get_settings().keep_versions
    if not keep:
        return 0
    cur = conn.execute("""DELETE FROM views.drawn_view_versions d
                           WHERE d.view_id = %(v)s
                             AND d.version_no <= (SELECT max(version_no) FROM views.drawn_view_versions WHERE view_id = %(v)s) - %(k)s
                             AND NOT EXISTS (SELECT 1 FROM views.tag_holds h WHERE h.view_id = d.view_id AND h.version_no = d.version_no)""",
                       {"v": view_id, "k": keep})
    return cur.rowcount or 0


def change(conn, model: str, actor: str, view: Any, data: dict) -> dict:
    v = _view(conn, model, view)
    name = _name(conn, model, data["name"], v["id"]) if data.get("name") is not None else v["name"]
    desc = (data.get("description") if data.get("description") is not None else v["description"])[:2000]
    conn.execute("""UPDATE views.drawn_views SET name = %(n)s, description = %(d)s, modified_by = %(u)s, modified_at = now()
                     WHERE id = %(v)s""", {"n": name, "d": desc, "u": actor, "v": v["id"]})
    return {"id": str(v["guid"]), "name": name, "description": desc, "message": f"Drawn view {name} changed."}


def delete(conn, model: str, actor: str, view: Any) -> dict:
    v = _view(conn, model, view)
    conn.execute("UPDATE views.drawn_views SET is_deleted = true, modified_by = %(u)s, modified_at = now() WHERE id = %(v)s",
                 {"u": actor, "v": v["id"]})
    return {"id": str(v["guid"]), "message": f"Drawn view {v['name']} removed (its versions are kept)."}


# ---------------------------------------------------------------- a model's own generated views (D406)

def _own(conn, model: str, view: Any) -> dict:
    """A view of the model's own by guid, by its code (MV-<n>) or by name."""
    code = re.fullmatch(r"MV-(\d+)", str(view).strip(), re.I)
    by = ("guid::text = %(v)s" if drawio.is_guid(view) else "id::text = %(v)s" if code
          else "lower(name) = lower(%(v)s)")
    view = code.group(1) if code else view
    v = one(conn, f"SELECT * FROM views.model_views WHERE model_guid::text = %(m)s AND NOT is_deleted AND {by}", m=str(model), v=str(view))
    if not v:
        raise Refused(f"This model has no view {view!r} of its own.", 404)
    return v


def _own_out(v: dict) -> dict:
    return {"id": str(v["guid"]), "code": f"MV-{v['id']}", "name": v["name"], "category": v["category"], "purpose": v["purpose"],
            "concerns": v["concerns"], "stakeholders": v["stakeholders"], "element_types": list(v["element_types"] or []),
            "relationship_types": list(v["relationship_types"] or []), "heat_attribute": v["heat_attribute"],
            "copied_from": v["copied_from"], "own": True, "created_by": v["created_by"], "modified_by": v["modified_by"],
            "modified_at": _ts(v["modified_at"])}


def _clean_definition(data: dict, partial: bool = False) -> dict:
    out = {}
    for k in VIEW_FIELDS:
        if k not in data and partial:
            continue
        val = data.get(k)
        if k in ("element_types", "relationship_types"):
            out[k] = [str(x).strip() for x in (val or []) if str(x).strip()]
        else:
            out[k] = " ".join(str(val or "").split()) if k == "name" else str(val or "").strip()
    if "element_types" in out and not out["element_types"]:
        raise Refused("Choose at least one element type.")
    if "heat_attribute" in out:
        out["heat_attribute"] = out["heat_attribute"] or "Lifecycle"
    if "category" in out:
        out["category"] = out["category"] or "Model"
    return out


def own_views(conn, model: str) -> dict:
    return {"model": str(model), "views": [_own_out(v) for v in rows(conn, """SELECT * FROM views.model_views
                                                                              WHERE model_guid::text = %(m)s AND NOT is_deleted
                                                                              ORDER BY lower(name)""", m=str(model))]}


def own_view(conn, model: str, view: Any) -> dict:
    return _own_out(_own(conn, model, view))


def add_own(conn, model: str, actor: str, data: dict) -> dict:
    """A view of the model's own: a copy of a standard view's definition (copied_from: its code) changed for this model."""
    d = _clean_definition(data)
    d["name"] = _name(conn, model, d["name"], table="model_views")
    v = one(conn, """INSERT INTO views.model_views (model_guid, name, category, purpose, concerns, stakeholders, element_types,
                                                    relationship_types, heat_attribute, copied_from, created_by, modified_by)
                     VALUES (CAST(%(m)s AS uuid), %(name)s, %(category)s, %(purpose)s, %(concerns)s, %(stakeholders)s,
                             %(element_types)s, %(relationship_types)s, %(heat_attribute)s, %(cf)s, %(u)s, %(u)s) RETURNING *""",
            m=str(model), cf=str(data.get("copied_from") or "")[:60], u=actor, **d)
    return {**_own_out(v), "message": f"View {d['name']} made for this model."}


def change_own(conn, model: str, actor: str, view: Any, data: dict) -> dict:
    v = _own(conn, model, view)
    d = _clean_definition(data, partial=True)
    if "name" in d:
        d["name"] = _name(conn, model, d["name"], v["id"], table="model_views")
    if d:
        sets = ", ".join(f"{k} = %({k})s" for k in d)
        conn.execute(f"UPDATE views.model_views SET {sets}, modified_by = %(u)s, modified_at = now() WHERE id = %(i)s",
                     {**d, "u": actor, "i": v["id"]})
    return {**_own_out(_own(conn, model, v["guid"])), "message": "View changed."}


def delete_own(conn, model: str, actor: str, view: Any) -> dict:
    v = _own(conn, model, view)
    conn.execute("UPDATE views.model_views SET is_deleted = true, modified_by = %(u)s, modified_at = now() WHERE id = %(i)s",
                 {"u": actor, "i": v["id"]})
    return {"id": str(v["guid"]), "message": f"View {v['name']} removed."}


# ---------------------------------------------------------------- for the main API: tags, copies, merges, packages

def hold_for_tag(conn, model: str, tag: str) -> list[dict]:
    """A tag keeps the views as they are now (D354): it holds each view's latest version, which is never dropped."""
    out = []
    for v in rows(conn, "SELECT * FROM views.drawn_views WHERE model_guid::text = %(m)s AND NOT is_deleted ORDER BY id", m=str(model)):
        ver = _latest(conn, v["id"])
        if not ver:
            continue
        conn.execute("""INSERT INTO views.tag_holds (tag_guid, model_guid, view_id, version_no)
                        VALUES (CAST(%(t)s AS uuid), CAST(%(m)s AS uuid), %(v)s, %(n)s)
                        ON CONFLICT (tag_guid, view_id) DO UPDATE SET version_no = EXCLUDED.version_no""",
                     {"t": str(tag), "m": str(model), "v": v["id"], "n": ver["version_no"]})
        out.append({"id": str(v["guid"]), "name": v["name"], "version": ver["version_no"]})
    return out


def tag_view(conn, model: str, tag: str, view: Any) -> dict:
    by = "v.guid::text = %(v)s" if drawio.is_guid(view) else "lower(v.name) = lower(%(v)s)"
    r = one(conn, f"""SELECT v.guid, v.name, x.version_no, x.xml, x.saved_by, x.saved_at
                        FROM views.tag_holds h JOIN views.drawn_views v ON v.id = h.view_id
                        JOIN views.drawn_view_versions x ON x.view_id = h.view_id AND x.version_no = h.version_no
                       WHERE h.tag_guid::text = %(t)s AND h.model_guid::text = %(m)s AND {by}""", t=str(tag), m=str(model), v=str(view))
    if not r:
        raise Refused(f"The tag keeps no drawn view {view!r}.", 404)
    return {"id": str(r["guid"]), "name": r["name"], "version": r["version_no"], "saved_by": r["saved_by"],
            "saved_at": _ts(r["saved_at"]), "xml": r["xml"], "read_only": True}


def export_model(conn, model: str, all_versions: bool = True) -> dict:
    """Everything of a model's views (a package, a backup): each drawn view with its versions, and its own views."""
    views = []
    for v in rows(conn, "SELECT * FROM views.drawn_views WHERE model_guid::text = %(m)s AND NOT is_deleted ORDER BY id", m=str(model)):
        vers = rows(conn, f"""SELECT version_no, xml, note, model_marker, saved_by, saved_at FROM views.drawn_view_versions
                               WHERE view_id = %(v)s ORDER BY version_no {'' if all_versions else 'DESC LIMIT 1'}""", v=v["id"])
        views.append({"id": str(v["guid"]), "name": v["name"], "description": v["description"], "source": v["source"],
                      "source_note": v["source_note"], "created_by": v["created_by"],
                      "versions": [dict(x, model_marker=_ts(x["model_marker"]), saved_at=_ts(x["saved_at"])) for x in sorted(vers, key=lambda x: x["version_no"])]})
    return {"drawn_views": views, "own_views": own_views(conn, model)["views"]}


def import_model(conn, model: str, data: dict, actor: str, ent_map: dict | None = None, rel_map: dict | None = None,
                 only_new: bool = False, source: str = "package", latest_only: bool = False, replace: bool = False) -> dict:
    """Views into a model: rebound to its entities and relationships (ent_map, rel_map: old guid -> new; an entity it does
    not have becomes a placeholder). only_new: only views it has no view of that name (a merge). A name taken gets
    " (copy)". latest_only: one version, the latest (copies and children). replace: a model backup put back over the model
    itself: its current views go first (they are in the model backup made just before), then the backup's come in."""
    ent_map, rel_map = dict(ent_map or {}), dict(rel_map or {})
    if replace:
        delete_model(conn, model, actor)
    have = {r["n"] for r in rows(conn, "SELECT lower(name) AS n FROM views.drawn_views WHERE model_guid::text = %(m)s AND NOT is_deleted",
                                 m=str(model))}
    made = 0
    for v in data.get("drawn_views") or []:
        vers = sorted(v.get("versions") or [], key=lambda x: x["version_no"])
        if not vers or (only_new and v["name"].lower() in have):
            continue
        if latest_only:
            vers = vers[-1:]
        name = v["name"]
        while name.lower() in have:
            name = f"{name} (copy)"
        have.add(name.lower())
        nv = one(conn, """INSERT INTO views.drawn_views (model_guid, name, description, source, source_note, created_by, modified_by)
                          VALUES (CAST(%(m)s AS uuid), %(n)s, %(d)s, %(s)s, %(sn)s, %(u)s, %(u)s) RETURNING id""",
                 m=str(model), n=name, d=v.get("description") or "", s=source if source in SOURCES else "package",
                 sn=f"{v['name']}, version {vers[-1]['version_no']}"[:300], u=v.get("created_by") or actor)
        for i, x in enumerate(vers, 1):
            note = x.get("note") or ""
            if latest_only:
                note = f"Copied from {v['name']} (version {x['version_no']})"
            _insert_version(conn, nv["id"], i if latest_only else x["version_no"], drawio.rebind(x["xml"], ent_map, rel_map)
                            if (ent_map or rel_map) else x["xml"], note, x.get("model_marker"), x.get("saved_by") or actor)
        made += 1
    own = 0
    taken = {r["n"] for r in rows(conn, "SELECT lower(name) AS n FROM views.model_views WHERE model_guid::text = %(m)s AND NOT is_deleted",
                                  m=str(model))}
    for o in data.get("own_views") or []:
        if o["name"].lower() in taken and only_new:
            continue
        name = o["name"]
        while name.lower() in taken:
            name = f"{name} (copy)"
        taken.add(name.lower())
        add_own(conn, model, o.get("created_by") or actor, {**o, "name": name})
        own += 1
    return {"drawn_views": made, "own_views": own}


def copy_model(conn, src: str, dst: str, actor: str, ent_map: dict, rel_map: dict, only_new: bool = False,
               source: str = "model-copy") -> dict:
    """A copied or child model gets the views (latest version each, bound to its own entities); a merge only the views
    the target lacks (D354)."""
    return import_model(conn, dst, export_model(conn, src, all_versions=False), actor, ent_map, rel_map, only_new=only_new,
                        source=source, latest_only=True)


def delete_model(conn, model: str, actor: str) -> dict:
    n = conn.execute("""UPDATE views.drawn_views SET is_deleted = true, modified_by = %(u)s, modified_at = now()
                         WHERE model_guid::text = %(m)s AND NOT is_deleted""", {"m": str(model), "u": actor}).rowcount
    k = conn.execute("""UPDATE views.model_views SET is_deleted = true, modified_by = %(u)s, modified_at = now()
                         WHERE model_guid::text = %(m)s AND NOT is_deleted""", {"m": str(model), "u": actor}).rowcount
    return {"drawn_views": n or 0, "own_views": k or 0}
