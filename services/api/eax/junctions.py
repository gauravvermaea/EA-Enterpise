"""Junctions (owner, 10 Nov 2026, D397, D402): And and Or junctions are repository objects of the model.

A junction is an entity of the model's connector type (core.entity_types.is_connector; in ArchiMate 4 based models the
type "Junction", with the attribute Junction Kind: And or Or). The metamodel lets every relationship type reach a
junction and leave it; the real rules are here, in Python (D248):

* every relationship through one junction is of one relationship type;
* each source that reaches it and each target it leads to must be allowed as if they were related directly;
* a junction end has no multiplicity (multiplicity is counted between elements);
* junctions joined to junctions are walked through, so a chain of junctions is checked end to end.

add_relationship (eax.content) calls check() before a relationship touching a junction is saved; the data quality
checks call problems() for every junction of the model.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .metamodel_edit import EditError


def _rows(conn, sql: str, **p) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), p).mappings().all()]


def connector_type_ids(conn, model_id: int) -> set[int]:
    return {r["id"] for r in _rows(conn, """SELECT id FROM core.entity_types
                                             WHERE model_id = :m AND is_connector AND NOT is_deleted""", m=model_id)}


def is_junction(conn, entity_id: int) -> bool:
    r = conn.execute(text("""SELECT t.is_connector FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                              WHERE e.id = :e"""), {"e": entity_id}).scalar()
    return bool(r)


def _rels_at(conn, junction_id: int) -> list[dict]:
    return _rows(conn, """SELECT r.id, r.relationship_type_id AS rt, r.source_entity_id AS s, r.target_entity_id AS t,
                                 rt.name AS rel
                            FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
                           WHERE NOT r.is_deleted AND (r.source_entity_id = :j OR r.target_entity_id = :j)""", j=junction_id)


def _ends(conn, junction_id: int, direction: str, seen: set[int] | None = None) -> set[int]:
    """The elements reaching the junction (direction 'in') or reached from it ('out'), through chains of junctions."""
    seen = seen or {junction_id}
    out: set[int] = set()
    for r in _rels_at(conn, junction_id):
        other = r["s"] if direction == "in" else r["t"]
        if (direction == "in" and r["t"] != junction_id) or (direction == "out" and r["s"] != junction_id):
            continue
        if other in seen:
            continue
        if is_junction(conn, other):
            seen.add(other)
            out |= _ends(conn, other, direction, seen)
        else:
            out.add(other)
    return out


def _type_of(conn, entity_id: int) -> tuple[int, str]:
    r = _rows(conn, """SELECT t.id, t.name FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                        WHERE e.id = :e""", e=entity_id)[0]
    return r["id"], r["name"]


def _allowed(conn, rt: int, s_type: int, t_type: int) -> bool:
    return bool(conn.execute(text("""SELECT 1 FROM core.allowed_relationships WHERE relationship_type_id = :r
                                      AND source_type_id = :s AND target_type_id = :t AND NOT is_deleted"""),
                             {"r": rt, "s": s_type, "t": t_type}).scalar())


def check(conn, src: int, tgt: int, rt: dict) -> None:
    """Before src -> tgt (relationship type rt: {_id, name}) is saved, when either end is a junction. Raises EditError."""
    for j, side in ((tgt, "in"), (src, "out")):
        if not is_junction(conn, j):
            continue
        kinds = {r["rt"] for r in _rels_at(conn, j)}
        if kinds and rt["_id"] not in kinds:
            names = ", ".join(sorted({r["rel"] for r in _rels_at(conn, j)}))
            raise EditError(f"Every relationship through one junction is of one type: this junction joins {names}, not "
                            f"{rt['name']} (D397).", 409)
        # each source reaching it, with each target it leads to, must be allowed as if direct
        new_end = src if side == "in" else tgt
        if is_junction(conn, new_end):
            continue                    # junction to junction: checked when elements reach both
        others = _ends(conn, j, "out" if side == "in" else "in")
        n_type, n_name = _type_of(conn, new_end)
        for o in others:
            o_type, o_name = _type_of(conn, o)
            s_t, t_t, s_n, t_n = (n_type, o_type, n_name, o_name) if side == "in" else (o_type, n_type, o_name, n_name)
            if not _allowed(conn, rt["_id"], s_t, t_t):
                raise EditError(f"Through this junction {s_n} would {rt['name'].lower()} {t_n}, which the metamodel does not "
                                f"allow directly (D397).", 409)
        if not others and not _could(conn, rt["_id"], n_type, side):
            raise EditError(f"No {rt['name']} {'from' if side == 'in' else 'to'} a {n_name} is allowed to anything, so it "
                            "cannot go through a junction (D397).", 409)


def _could(conn, rt: int, type_id: int, side: str) -> bool:
    """Whether the type has any allowed relationship of this type, towards any element (not a junction)."""
    col, other = ("source_type_id", "target_type_id") if side == "in" else ("target_type_id", "source_type_id")
    return bool(conn.execute(text(f"""SELECT 1 FROM core.allowed_relationships a JOIN core.entity_types o ON o.id = a.{other}
                                       WHERE a.relationship_type_id = :r AND a.{col} = :t AND NOT a.is_deleted
                                         AND NOT o.is_connector LIMIT 1"""), {"r": rt, "t": type_id}).scalar())


def problems(conn, model_id: int) -> dict[int, list[str]]:
    """For the data quality checks: each junction's broken rules, by its entity id."""
    out: dict[int, list[str]] = {}
    js = _rows(conn, """SELECT e.id FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                         WHERE e.model_id = :m AND t.is_connector AND NOT e.is_deleted""", m=model_id)
    for j in js:
        rels = _rels_at(conn, j["id"])
        why = []
        kinds = {r["rel"] for r in rels}
        if len(kinds) > 1:
            why.append(f"Joins relationships of more than one type ({', '.join(sorted(kinds))})")
        if rels and not any(r["t"] == j["id"] for r in rels):
            why.append("Nothing reaches it")
        if rels and not any(r["s"] == j["id"] for r in rels):
            why.append("It leads nowhere")
        if len(kinds) == 1:
            rt = rels[0]["rt"]
            for s in _ends(conn, j["id"], "in"):
                for t in _ends(conn, j["id"], "out"):
                    (s_t, s_n), (t_t, t_n) = _type_of(conn, s), _type_of(conn, t)
                    if not _allowed(conn, rt, s_t, t_t):
                        why.append(f"{s_n} to {t_n} through it is not allowed directly ({rels[0]['rel']})")
        if why:
            out[j["id"]] = sorted(set(why))
    return out


def kind_of(values: dict[str, Any] | None) -> str:
    """And or Or from an entity's values (Junction Kind); And when not set."""
    v = (values or {}).get("JunctionKind") or (values or {}).get("Junction Kind") or "And"
    return "Or" if str(v).strip().lower() == "or" else "And"
