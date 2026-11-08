"""Search, saved views and favourites (build phase 7).

Search looks through every model the person may read (row security on the tables decides), in names,
display IDs, descriptions, tags and attribute values, with filters for model, entity type, attribute and
tag. Saved views keep a grid's or list's columns, filters and sort, private or shared with everyone who
can read the model. Favourites mark entities, models and views to find again.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from . import repository as repo
from .metamodel_edit import EditError


def _rows(conn, sql: str, **p) -> list[dict]:
    return repo._rows(conn, sql, **p)


def _one(conn, sql: str, **p) -> dict | None:
    rows = _rows(conn, sql, **p)
    return rows[0] if rows else None


# ---------------------------------------------------------------- search
def search(conn, q: str = "", model: Any = None, entity_type: str = "", attribute: str = "", tag: str = "",
           status: str = "", limit: int = 100) -> dict:
    """Entities matching the text in their name, display ID, description, tags or any attribute value (or
    only the given attribute), with the field that matched. Filters: model, entity type (name or code),
    tag, status. At most `limit` results, best first (exact names, then names, then the rest)."""
    q = (q or "").strip()
    if not q and not tag and not entity_type:
        return {"query": q, "results": [], "total": 0}
    m = repo.get_model(conn, model) if model else None
    limit = max(1, min(int(limit or 100), 500))
    like = f"%{q}%"
    attr_filter = "AND (lower(at.code) = lower(:attr) OR lower(at.name) = lower(:attr))" if attribute else ""
    rows = _rows(conn, f"""
        WITH hits AS (
            SELECT e.id, CASE WHEN lower(e.name) = lower(:q) THEN 0 WHEN e.name ILIKE :like THEN 1
                              WHEN e.display_id ILIKE :like THEN 2 ELSE 4 END AS rank,
                   CASE WHEN e.name ILIKE :like THEN 'Name' WHEN e.display_id ILIKE :like THEN 'Display ID'
                        WHEN e.description ILIKE :like THEN 'Description' ELSE 'Tags' END AS field,
                   CASE WHEN e.description ILIKE :like AND NOT e.name ILIKE :like THEN left(e.description, 160) ELSE '' END AS snippet
              FROM core.entities e
             WHERE NOT e.is_deleted AND :attr = '' AND :q <> ''
               AND (e.name ILIKE :like OR e.display_id ILIKE :like OR e.description ILIKE :like
                    OR EXISTS (SELECT 1 FROM unnest(e.tags) t WHERE t ILIKE :like))
            UNION ALL
            SELECT av.entity_id, 3, at.name,
                   coalesce(av.value_text, av.value_number::text, av.value_date::text,
                            CASE WHEN av.value_bool THEN 'Yes' WHEN NOT av.value_bool THEN 'No' END, re.name)
              FROM core.attribute_values av JOIN core.attribute_types at ON at.id = av.attribute_type_id
              LEFT JOIN core.entities re ON re.id = av.value_ref
             WHERE NOT av.is_deleted AND av.entity_id IS NOT NULL AND :q <> '' {attr_filter}
               AND (av.value_text ILIKE :like OR av.value_number::text = :q OR av.value_date::text LIKE :q || '%'
                    OR re.name ILIKE :like)
            UNION ALL
            SELECT e.id, 5, 'Type or tag', '' FROM core.entities e WHERE NOT e.is_deleted AND :q = ''
        ), best AS (
            SELECT DISTINCT ON (id) id, rank, field, snippet FROM hits ORDER BY id, rank
        )
        SELECT e.guid AS id, e.display_id, e.name, e.status_code AS status, e.tags, et.name AS entity_type,
               et.guid AS entity_type_id, l.colour, m.guid AS model_id, m.name AS model, b.field, b.snippet, b.rank
          FROM best b JOIN core.entities e ON e.id = b.id
          JOIN core.entity_types et ON et.id = e.entity_type_id JOIN core.layers l ON l.id = et.layer_id
          JOIN core.models m ON m.id = e.model_id AND NOT m.is_deleted
         WHERE (CAST(:m AS bigint) IS NULL OR e.model_id = :m)
           AND (:etype = '' OR lower(et.name) = lower(:etype) OR lower(et.code) = lower(:etype))
           AND (:tag = '' OR lower(:tag) = ANY (e.tags))
           AND (:status = '' OR e.status_code = :status)
         ORDER BY b.rank, e.name LIMIT :n""",
                 q=q, like=like, attr=attribute or "", m=m["_id"] if m else None, etype=entity_type or "",
                 tag=(tag or "").strip().lower(), status=status or "", n=limit + 1)
    more = len(rows) > limit
    for r in rows:
        r.pop("rank", None)
    return {"query": q, "results": rows[:limit], "total": len(rows[:limit]), "more": more}


# ---------------------------------------------------------------- saved views
def _model_id(conn, model: Any) -> int | None:
    return repo.get_model(conn, model)["_id"] if model else None


def list_views(conn, username: str, model: Any = None, view_kind: str = "", target: str = "") -> list[dict]:
    """The person's own views and those shared with them (on models they may read)."""
    mid = _model_id(conn, model)
    return _rows(conn, """
        SELECT v.guid AS id, v.name, v.view_kind, v.target, v.config, v.shared, v.owner, m.guid AS model_id,
               v.owner = lower(:u) AS mine, v.modified_at
          FROM core.saved_views v LEFT JOIN core.models m ON m.id = v.model_id
         WHERE (v.owner = lower(:u) OR (v.shared AND (v.model_id IS NULL OR core.can_read_model(v.model_id))))
           AND (CAST(:m AS bigint) IS NULL OR v.model_id = :m)
           AND (:k = '' OR v.view_kind = :k) AND (:t = '' OR v.target = :t)
         ORDER BY (v.owner = lower(:u)) DESC, lower(v.name)""", u=username, m=mid, k=view_kind or "", t=target or "")


def save_view(conn, username: str, data: dict) -> dict:
    name = (data.get("name") or "").strip()
    if not name:
        raise EditError("Give the view a name.")
    if data.get("view_kind") not in ("entity_grid", "relationship_grid", "metamodel_grid", "search", "type_table"):
        raise EditError("Unknown kind of view.")
    mid = _model_id(conn, data.get("model"))
    config = json.dumps(data.get("config") or {})
    if data.get("id"):
        cur = _one(conn, "SELECT id, owner FROM core.saved_views WHERE guid = CAST(:g AS uuid)", g=str(data["id"]))
        if not cur:
            raise EditError("No such view.", 404)
        if cur["owner"] != username.lower():
            raise EditError(f"Only {cur['owner']}, who made this view, can change it. Save it as a new view instead.", 403)
        conn.execute(text("""UPDATE core.saved_views SET name = :n, config = CAST(:c AS jsonb), shared = :s, modified_at = now()
                             WHERE id = :i"""), {"n": name, "c": config, "s": bool(data.get("shared")), "i": cur["id"]})
        guid = str(data["id"])
    else:
        guid = conn.execute(text("""INSERT INTO core.saved_views (owner, model_id, view_kind, target, name, config, shared)
                                    VALUES (lower(:u), :m, :k, :t, :n, CAST(:c AS jsonb), :s) RETURNING guid"""),
                            {"u": username, "m": mid, "k": data["view_kind"], "t": data.get("target") or "", "n": name,
                             "c": config, "s": bool(data.get("shared"))}).scalar_one()
    return {"id": str(guid), "name": name}


def delete_view(conn, username: str, view: str) -> dict:
    cur = _one(conn, "SELECT id, owner FROM core.saved_views WHERE guid = CAST(:g AS uuid)", g=str(view))
    if not cur:
        raise EditError("No such view.", 404)
    if cur["owner"] != username.lower():
        raise EditError(f"Only {cur['owner']}, who made this view, can delete it.", 403)
    conn.execute(text("DELETE FROM core.favourites WHERE kind = 'view' AND target = CAST(:g AS uuid)"), {"g": str(view)})
    conn.execute(text("DELETE FROM core.saved_views WHERE id = :i"), {"i": cur["id"]})
    return {"deleted": str(view)}


# ---------------------------------------------------------------- favourites
def list_favourites(conn, username: str) -> list[dict]:
    """The person's favourites that still exist and that they may still read, newest first."""
    return _rows(conn, """
        SELECT f.kind, f.target AS id, f.created_at,
               coalesce(e.name, m.name, v.name, f.label) AS name, e.display_id, et.name AS entity_type,
               coalesce(em.guid, m.guid, vm.guid) AS model_id, coalesce(em.name, m.name, vm.name) AS model
          FROM core.favourites f
          LEFT JOIN core.entities e ON f.kind = 'entity' AND e.guid = f.target AND NOT e.is_deleted
          LEFT JOIN core.entity_types et ON et.id = e.entity_type_id
          LEFT JOIN core.models em ON em.id = e.model_id
          LEFT JOIN core.models m ON f.kind = 'model' AND m.guid = f.target AND NOT m.is_deleted
          LEFT JOIN core.saved_views v ON f.kind = 'view' AND v.guid = f.target
          LEFT JOIN core.models vm ON vm.id = v.model_id
         WHERE f.username = lower(:u) AND (e.id IS NOT NULL OR m.id IS NOT NULL OR v.id IS NOT NULL OR f.kind = 'project')
         ORDER BY f.created_at DESC""", u=username)


def set_favourite(conn, username: str, kind: str, target: str, on: bool, label: str = "") -> dict:
    if kind not in ("entity", "model", "view", "project"):
        raise EditError("A favourite is an entity, a model, a view or a project.")
    if on:
        conn.execute(text("""INSERT INTO core.favourites (username, kind, target, label) VALUES (lower(:u), :k, CAST(:t AS uuid), :l)
                             ON CONFLICT (username, kind, target) DO NOTHING"""), {"u": username, "k": kind, "t": str(target), "l": label or ""})
    else:
        conn.execute(text("DELETE FROM core.favourites WHERE username = lower(:u) AND kind = :k AND target = CAST(:t AS uuid)"),
                     {"u": username, "k": kind, "t": str(target)})
    return {"kind": kind, "id": str(target), "favourite": on}
