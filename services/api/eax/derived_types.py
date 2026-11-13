"""Entity types derived from another (R2.9, D629; owner, 11 Nov 2026: "Server -> Windows Server -> DB Server or Web
Server"; answers 12 Nov 2026, 21:37).

A design-time decision in the metamodel, recorded as ArchiMate's Specialization between the two types
(core.entity_types.base_type_id), never between entities:

* the base and the derived type are in the same metamodel; any type may be a base; no type derives from itself, at any
  depth;
* the derived type gets the base type's attributes and allowed relationships, plus its own: they are copied onto it
  (item_attributes and allowed_relationships with inherited_from) each time a metamodel change is applied, which
  publishes a metamodel version, so a change to the base flows down then;
* what the derived type sets itself wins (its own attribute of the same kind is left as it is);
* an attribute the base no longer has stays on the derived type, retired, with the values already captured (nothing is
  lost); an allowed relationship the base no longer has is retired the same way;
* each entity keeps all its own values; nothing is read from the base when data is entered or reported, so grids, views
  and reports show each type on its own.

No logic in the database (D248): the application does all of this.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .metamodel_edit import EditError

ITEM_FIELDS = ("is_required", "section", "default_value", "help_text", "quality_weight")


def _rows(conn, sql: str, **p) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), p).mappings()]


def chain(conn, type_id: int) -> list[int]:
    """The type and its bases, nearest first (stops at a loop)."""
    out, seen, cur = [], set(), type_id
    while cur and cur not in seen:
        seen.add(cur)
        out.append(cur)
        cur = conn.execute(text("SELECT base_type_id FROM core.entity_types WHERE id = :i AND NOT is_deleted"), {"i": cur}).scalar()
    return out


def check_base(conn, model_id: int, type_id: int | None, base_id: int) -> None:
    """A base in the same metamodel, not the type itself and not one derived from it (no loop)."""
    b = conn.execute(text("SELECT id, model_id, name FROM core.entity_types WHERE id = :i AND NOT is_deleted"),
                     {"i": base_id}).mappings().first()
    if not b or int(b["model_id"]) != int(model_id):
        raise EditError("The base type must be an entity type of the same metamodel.")
    if type_id is not None and type_id in chain(conn, base_id):
        raise EditError(f"{b['name']} is this type or derives from it: a type cannot derive from itself.")


def ordered(conn, model_id: int) -> list[dict]:
    """The derived types of a metamodel, each after its base (so a change flows down every level in one pass)."""
    rows = _rows(conn, """SELECT id, base_type_id AS base FROM core.entity_types
                           WHERE model_id = :m AND base_type_id IS NOT NULL AND NOT is_deleted""", m=model_id)
    by = {r["id"]: r for r in rows}
    out, done = [], set()

    def visit(r, path=()):
        if r["id"] in done or r["id"] in path:
            return
        if r["base"] in by:
            visit(by[r["base"]], (*path, r["id"]))
        done.add(r["id"])
        out.append(r)
    for r in rows:
        visit(r)
    return out


def sync(conn, model_id: int) -> dict:
    """Copies each base type's attributes and allowed relationships onto the types derived from it."""
    counts = {"attributes_added": 0, "attributes_changed": 0, "attributes_retired": 0, "allowed_added": 0, "allowed_retired": 0}
    for t in ordered(conn, model_id):
        _attributes(conn, model_id, t["id"], t["base"], counts)
        _allowed(conn, model_id, t["id"], t["base"], counts)
    return counts


def _attributes(conn, mid: int, tid: int, base: int, counts: dict) -> None:
    base_items = _rows(conn, f"""SELECT id, attribute_type_id, sort_order, {", ".join(ITEM_FIELDS)} FROM core.item_attributes
                                 WHERE entity_type_id = :b AND NOT is_deleted AND status_code <> 'retired'""", b=base)
    mine = {r["attribute_type_id"]: r for r in _rows(conn, f"""SELECT id, attribute_type_id, inherited_from, {", ".join(ITEM_FIELDS)}
                                                               FROM core.item_attributes WHERE entity_type_id = :t AND NOT is_deleted""", t=tid)}
    live = set()
    for bi in base_items:
        have = mine.get(bi["attribute_type_id"])
        vals = {k: bi[k] for k in ITEM_FIELDS}
        if have is None:
            conn.execute(text(f"""INSERT INTO core.item_attributes (model_id, attribute_type_id, entity_type_id, sort_order,
                                                                    inherited_from, {", ".join(ITEM_FIELDS)})
                                  VALUES (:m, :a, :t, :so, :inh, {", ".join(":" + k for k in ITEM_FIELDS)})"""),
                         {"m": mid, "a": bi["attribute_type_id"], "t": tid, "so": bi["sort_order"], "inh": bi["id"], **vals})
            counts["attributes_added"] += 1
            live.add(bi["id"])
        elif have["inherited_from"] is not None:       # one it got from a base: follows the base's changes
            live.add(bi["id"])
            if have["inherited_from"] != bi["id"] or any(have[k] != vals[k] for k in ITEM_FIELDS):
                sets = ", ".join(f"{k} = :{k}" for k in ITEM_FIELDS)
                conn.execute(text(f"""UPDATE core.item_attributes SET {sets}, inherited_from = :inh, status_code = 'published'
                                      WHERE id = :i"""), {"i": have["id"], "inh": bi["id"], **vals})
                counts["attributes_changed"] += 1
        # its own attribute of the same kind wins: left as it is
    for have in mine.values():
        if have["inherited_from"] is not None and have["inherited_from"] not in live:
            # the base no longer has it: kept with its values, retired, and the type's own from now on
            conn.execute(text("UPDATE core.item_attributes SET status_code = 'retired', inherited_from = NULL WHERE id = :i"),
                         {"i": have["id"]})
            counts["attributes_retired"] += 1


def _allowed(conn, mid: int, tid: int, base: int, counts: dict) -> None:
    base_rows = _rows(conn, """SELECT id, relationship_type_id AS r, source_type_id AS s, target_type_id AS t, note,
                                      source_multiplicity, target_multiplicity
                                 FROM core.allowed_relationships
                                WHERE (source_type_id = :b OR target_type_id = :b) AND NOT is_deleted AND status_code <> 'retired'""", b=base)
    live = set()
    for a in base_rows:
        s = tid if a["s"] == base else a["s"]
        t = tid if a["t"] == base else a["t"]
        have = conn.execute(text("""SELECT id, inherited_from FROM core.allowed_relationships WHERE relationship_type_id = :r
                                     AND source_type_id = :s AND target_type_id = :t AND NOT is_deleted"""),
                            {"r": a["r"], "s": s, "t": t}).mappings().first()
        if have is None:
            conn.execute(text("""INSERT INTO core.allowed_relationships (model_id, relationship_type_id, source_type_id, target_type_id,
                                                                         note, source_multiplicity, target_multiplicity, inherited_from)
                                 VALUES (:m, :r, :s, :t, :n, :sm, :tm, :inh)"""),
                         {"m": mid, "r": a["r"], "s": s, "t": t, "n": a["note"] or "", "sm": a["source_multiplicity"],
                          "tm": a["target_multiplicity"], "inh": a["id"]})
            counts["allowed_added"] += 1
            live.add((a["r"], s, t))
        elif have["inherited_from"] is not None:
            live.add((a["r"], s, t))
            if have["inherited_from"] != a["id"]:
                conn.execute(text("UPDATE core.allowed_relationships SET inherited_from = :inh, status_code = 'published' WHERE id = :i"),
                             {"i": have["id"], "inh": a["id"]})
    for have in _rows(conn, """SELECT id, relationship_type_id AS r, source_type_id AS s, target_type_id AS t
                                 FROM core.allowed_relationships
                                WHERE (source_type_id = :t OR target_type_id = :t) AND inherited_from IS NOT NULL AND NOT is_deleted""",
                      t=tid):
        if (have["r"], have["s"], have["t"]) not in live:
            conn.execute(text("UPDATE core.allowed_relationships SET status_code = 'retired', inherited_from = NULL WHERE id = :i"),
                         {"i": have["id"]})
            counts["allowed_retired"] += 1


def set_base(conn, model_id: int, type_id: int, base_ref: Any, find) -> str:
    """Sets (or with '' clears) a type's base. find(ref) gives the base's row. Clearing keeps what was copied, as the
    type's own. Returns the base's name, or ''."""
    if base_ref in (None, ""):
        conn.execute(text("UPDATE core.entity_types SET base_type_id = NULL WHERE id = :i"), {"i": type_id})
        conn.execute(text("UPDATE core.item_attributes SET inherited_from = NULL WHERE entity_type_id = :i"), {"i": type_id})
        conn.execute(text("""UPDATE core.allowed_relationships SET inherited_from = NULL
                              WHERE (source_type_id = :i OR target_type_id = :i) AND inherited_from IS NOT NULL"""), {"i": type_id})
        return ""
    b = find(base_ref)
    check_base(conn, model_id, type_id, b["id"])
    conn.execute(text("UPDATE core.entity_types SET base_type_id = :b WHERE id = :i"), {"b": b["id"], "i": type_id})
    return b["name"]


def copied(conn, src_id: int, dst_id: int) -> None:
    """After a metamodel is copied into another model (core.copy_model, matched by codes): each type's base, and which
    attributes and allowed relationships came from the base, as in the source."""
    conn.execute(text("""UPDATE core.entity_types d SET base_type_id = db.id
                           FROM core.entity_types s JOIN core.entity_types sb ON sb.id = s.base_type_id, core.entity_types db
                          WHERE s.model_id = :s AND d.model_id = :d AND lower(d.code) = lower(s.code)
                            AND db.model_id = :d AND lower(db.code) = lower(sb.code) AND NOT db.is_deleted
                            AND d.base_type_id IS DISTINCT FROM db.id"""), {"s": src_id, "d": dst_id})
    conn.execute(text("""UPDATE core.item_attributes di SET inherited_from = dbi.id
                           FROM core.item_attributes si
                           JOIN core.entity_types st ON st.id = si.entity_type_id
                           JOIN core.attribute_types sa ON sa.id = si.attribute_type_id,
                                core.entity_types dt, core.attribute_types da, core.item_attributes dbi
                          WHERE si.model_id = :s AND si.inherited_from IS NOT NULL AND NOT si.is_deleted
                            AND dt.model_id = :d AND lower(dt.code) = lower(st.code) AND dt.base_type_id IS NOT NULL
                            AND da.model_id = :d AND lower(da.code) = lower(sa.code)
                            AND di.entity_type_id = dt.id AND di.attribute_type_id = da.id AND NOT di.is_deleted
                            AND dbi.entity_type_id = dt.base_type_id AND dbi.attribute_type_id = da.id AND NOT dbi.is_deleted"""),
                 {"s": src_id, "d": dst_id})
    conn.execute(text("""UPDATE core.item_attributes di SET status_code = 'retired'
                           FROM core.item_attributes si JOIN core.entity_types st ON st.id = si.entity_type_id
                           JOIN core.attribute_types sa ON sa.id = si.attribute_type_id, core.entity_types dt, core.attribute_types da
                          WHERE si.model_id = :s AND si.status_code = 'retired' AND NOT si.is_deleted
                            AND dt.model_id = :d AND lower(dt.code) = lower(st.code) AND da.model_id = :d AND lower(da.code) = lower(sa.code)
                            AND di.entity_type_id = dt.id AND di.attribute_type_id = da.id AND NOT di.is_deleted
                            AND di.status_code <> 'retired'"""), {"s": src_id, "d": dst_id})     # a retired one stays retired
    # the allowed relationships: those a derived type has that its base also has (by the base in place of it) are its
    # base's again; sync() then links each one to the base's row
    conn.execute(text("""UPDATE core.allowed_relationships d SET inherited_from = b.id
                           FROM core.entity_types t, core.allowed_relationships b
                          WHERE d.model_id = :d AND NOT d.is_deleted AND d.inherited_from IS NULL
                            AND t.model_id = :d AND t.base_type_id IS NOT NULL AND (d.source_type_id = t.id OR d.target_type_id = t.id)
                            AND b.relationship_type_id = d.relationship_type_id AND NOT b.is_deleted
                            AND b.source_type_id = CASE WHEN d.source_type_id = t.id THEN t.base_type_id ELSE d.source_type_id END
                            AND b.target_type_id = CASE WHEN d.target_type_id = t.id THEN t.base_type_id ELSE d.target_type_id END
                            AND EXISTS (SELECT 1 FROM core.allowed_relationships s
                                          JOIN core.entity_types ss ON ss.id = s.source_type_id JOIN core.entity_types sd ON sd.id = s.target_type_id
                                          JOIN core.relationship_types sr ON sr.id = s.relationship_type_id
                                          JOIN core.relationship_types dr ON dr.id = d.relationship_type_id
                                          JOIN core.entity_types ds ON ds.id = d.source_type_id JOIN core.entity_types dd ON dd.id = d.target_type_id
                                         WHERE s.model_id = :s AND s.inherited_from IS NOT NULL AND NOT s.is_deleted
                                           AND lower(sr.code) = lower(dr.code) AND lower(ss.code) = lower(ds.code)
                                           AND lower(sd.code) = lower(dd.code))"""), {"s": src_id, "d": dst_id})
    sync(conn, dst_id)
