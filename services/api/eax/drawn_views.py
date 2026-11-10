"""Drawn views (phases 28 and 29; owner, 9 and 10 Nov 2026, D354, D387 to D402).

A drawn view is a draw.io file of its model, kept with its versions by the views service (its own database, D405;
eax.views_client): the screens open and save views there, and it asks this API who may draw and whether a view's
objects are the model's own (access, check below). The repository is the truth; a view only shows it:

* a shape bound to the model carries ea_id (the entity's guid) and ea_type; a placeholder carries ea_type and
  ea_placeholder="1" until it is realised; a line carries ea_rel (the type) and ea_rel_id (the relationship's guid);
  the hidden lines are a JSON list in ea_hidden on the root cell;
* a view holds only its own model's entities (checked on every save; D354);
* relationships are made in the platform (as the person's uncommitted change, eax.commits), never in the file.

Here, what needs the model's data: who may draw and the model's last change (access), the check that a view holds
only the model's entities (check), the plugin's setup, what is current for the entities on a view (resync), the
relationships to draw when an entity is placed, a view's xml built in Python (MCP, the sample data, "Save as a drawn
view"), entities' own icons, heat maps, a view as a project's evidence, and the maps that bind a copied or child
model's views to its own entities.
"""

from __future__ import annotations

import base64
import json
import urllib.parse
import zlib
from typing import Any
from xml.sax.saxutils import quoteattr

from defusedxml import ElementTree as SafeET
from sqlalchemy import text

from . import notation
from . import repository as repo
from .metamodel_edit import EditError

MAX_XML = 5_000_000           # characters: a drawn view is a picture, not a store
MAX_ICON = 64 * 1024          # bytes (D354): an icon is small


def _rows(conn, sql: str, **p) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), p).mappings().all()]


def _one(conn, sql: str, **p) -> dict | None:
    r = conn.execute(text(sql), p).mappings().first()
    return dict(r) if r else None


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


def _ts(v: Any) -> str | None:
    return v.isoformat() if hasattr(v, "isoformat") else _s(v)


# ---------------------------------------------------------------- the draw.io file

def _graph_models(root) -> list:
    """The mxGraphModel elements of a file (an mxfile with diagrams, compressed or not, or a bare mxGraphModel)."""
    if root.tag == "mxGraphModel":
        return [root]
    out = []
    for d in root.iter("diagram"):
        inner = d.find("mxGraphModel")
        if inner is not None:
            out.append(inner)
        elif (d.text or "").strip():
            try:
                raw = zlib.decompress(base64.b64decode(d.text.strip()), -15).decode("utf-8")
                out.append(SafeET.fromstring(urllib.parse.unquote(raw)))
            except Exception as exc:  # noqa: BLE001
                raise EditError("A page of this draw.io file cannot be read.") from exc
    return out


def parse(xml: str) -> dict:
    """What a draw.io file shows: its objects (bound, placeholders, junctions), its relationship lines, the hidden list.
    Raises EditError when it is not a draw.io file."""
    if not xml or not xml.strip():
        raise EditError("The view is empty: no draw.io file was sent.")
    if len(xml) > MAX_XML:
        raise EditError(f"The view is too large ({len(xml) // 1000} k characters; at most {MAX_XML // 1000} k).", 413)
    try:
        root = SafeET.fromstring(xml)
    except Exception as exc:  # noqa: BLE001  (defusedxml refuses entities and the like, too)
        raise EditError("This is not a draw.io file that can be read.") from exc
    if root.tag not in ("mxfile", "mxGraphModel"):
        raise EditError("This is not a draw.io file (no mxfile or mxGraphModel).")
    objects, lines, hidden, placeholders, cells = [], [], [], 0, 0
    for gm in _graph_models(root):
        r = gm.find("root")
        if r is None:
            continue
        for el in list(r):
            cells += 1
            attrs = dict(el.attrib)
            cell = el.find("mxCell") if el.tag in ("object", "UserObject") else el
            cattrs = dict(cell.attrib) if cell is not None else {}
            cid = attrs.get("id") or cattrs.get("id")
            if cid == "0" and attrs.get("ea_hidden"):
                try:
                    hidden = [h for h in json.loads(attrs["ea_hidden"]) if isinstance(h, dict)]
                except ValueError:
                    hidden = []
            if cattrs.get("edge") == "1" and attrs.get("ea_rel"):
                lines.append({"cell": cid, "type": attrs.get("ea_rel"), "id": attrs.get("ea_rel_id") or None,
                              "source_cell": cattrs.get("source"), "target_cell": cattrs.get("target"),
                              "uncommitted": attrs.get("ea_uncommitted") == "1"})
            elif cattrs.get("vertex") == "1" and attrs.get("ea_junction_kind"):     # a junction (the plugin's cells)
                objects.append({"cell": cid, "entity": attrs.get("ea_junction") or None, "type": "Junction",
                                "label": "", "placeholder": False, "junction": attrs["ea_junction_kind"].lower()})
            elif cattrs.get("vertex") == "1" and (attrs.get("ea_id") or attrs.get("ea_type")):
                o = {"cell": cid, "entity": attrs.get("ea_id") or None, "type": attrs.get("ea_type") or "",
                     "label": attrs.get("label", ""), "placeholder": attrs.get("ea_placeholder") == "1" and not attrs.get("ea_id")}
                placeholders += o["placeholder"]
                objects.append(o)
    by_cell = {o["cell"]: o["entity"] for o in objects}
    for line in lines:
        line["source"] = by_cell.get(line.pop("source_cell"))
        line["target"] = by_cell.get(line.pop("target_cell"))
    return {"objects": objects, "relationships": lines, "hidden": hidden, "placeholders": placeholders, "cells": cells,
            "entities": sorted({o["entity"] for o in objects if o["entity"]})}


def check(conn, model: Any, entities: list[str], relationships: list[str]) -> dict:
    """A view holds only this model's entities and relationships (D354), asked by the views service on every save.
    Raises EditError when not; returns how many of the entities are missing or deleted."""
    m = repo.get_model(conn, model)
    ids = [e for e in entities or [] if repo._as_guid(e)]
    bad = [e for e in entities or [] if not repo._as_guid(e)]
    if bad:
        raise EditError(f"An object on the view is bound to {bad[0]!r}, which is not an entity id.")
    rows = _rows(conn, """SELECT e.guid::text AS id, e.model_id, e.is_deleted FROM core.entities e
                           WHERE e.guid = ANY(CAST(:ids AS uuid[]))""", ids=ids) if ids else []
    found = {r["id"]: r for r in rows}
    foreign = [i for i in ids if i in found and found[i]["model_id"] != m["_id"]]
    if foreign:
        raise EditError(f"A drawn view holds only its own model's entities (D354): {len(foreign)} object(s) on it belong to "
                        "another model. Draw them in that model, or copy the view into it.")
    rel_ids = [r for r in relationships or [] if repo._as_guid(r)]
    rrows = _rows(conn, """SELECT guid::text AS id, model_id FROM core.relationships WHERE guid = ANY(CAST(:ids AS uuid[]))""",
                  ids=rel_ids) if rel_ids else []
    if any(r["model_id"] != m["_id"] for r in rrows):
        raise EditError("A line on the view is a relationship of another model (D354).")
    return {"entities": len(ids), "missing_entities": len([i for i in ids if i not in found]),
            "deleted_entities": len([i for i in ids if i in found and found[i]["is_deleted"]])}


# ---------------------------------------------------------------- who may draw; the views service's files

def marker(conn, model_id: int):
    """The model's last content change (entities and relationships), compared with a saved view's (D354 banner)."""
    return conn.execute(text("""SELECT greatest((SELECT max(modified_at) FROM core.entities WHERE model_id = :m),
                                                (SELECT max(modified_at) FROM core.relationships WHERE model_id = :m))"""),
                        {"m": model_id}).scalar()


def may_draw(conn, who, m: dict) -> None:
    """Anyone who may change the model's content draws and saves its views (D354); used where no route checks it (MCP)."""
    from . import permissions
    if not permissions.allowed(who.roles, "model.content", permissions.model_roles(conn, who.username, m["id"])):
        raise EditError(f"Not allowed: drawing views of {m['name']} needs a role on it that may change its content.", 403)


def _writable(m: dict) -> None:
    """A frozen, archived or locked model keeps its drawn views as they are."""
    if m.get("frozen_at") or (m.get("lock_level") or "") in ("content", "maintenance") or m.get("lifecycle") == "archived" \
            or m.get("kind") == "template":
        raise EditError(f"{m['name']} is frozen, locked or archived: its drawn views open read only.", 409)


def access(conn, model: Any, user) -> dict:
    """For the views service (D405): the model as this person sees it (reading it is checked by the route), whether they
    may draw its views (and why not), and the model's last content change (for "the model changed since")."""
    m = repo.get_model(conn, model)
    reason = None
    try:
        _writable(m)
        may_draw(conn, user, m)
    except EditError as exc:
        reason = str(exc)
    mk = marker(conn, m["_id"])
    return {"id": str(m["id"]), "name": m["name"], "may_draw": reason is None, "read_only_reason": reason,
            "marker": mk.isoformat() if hasattr(mk, "isoformat") else mk}


def _blank() -> str:
    return build_xml([], [])


def _view_xml(m: dict, view: Any, version: int | None = None) -> str:
    """A view's file, from the views service."""
    from . import views_client as vc
    try:
        return vc.get_view(m["id"], view, version).get("xml") or _blank()
    except vc.ViewsDown as exc:
        raise EditError(f"The drawn view cannot be read: {exc}", exc.status if exc.status in (403, 404, 409) else 503) from exc


# ---------------------------------------------------------------- what is current: resync and placing

def _entities(conn, m: dict, ids: list[str]) -> dict[str, dict]:
    ids = [i for i in ids if repo._as_guid(i)]
    if not ids:
        return {}
    rows = _rows(conn, """SELECT e.guid::text AS id, e.id AS _id, e.name, e.display_id, e.is_deleted, t.code AS type,
                                 t.name AS type_name, t.notation, t.fill_colour, t.is_connector, l.colour AS domain_colour,
                                 l.name AS domain, i.content_type AS icon_type, i.content AS icon
                            FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                            JOIN core.layers l ON l.id = t.layer_id
                            LEFT JOIN core.entity_icons i ON i.entity_id = e.id
                           WHERE e.model_id = :m AND e.guid = ANY(CAST(:ids AS uuid[]))""", m=m["_id"], ids=ids)
    kinds = {r["entity_id"]: r["v"] for r in _rows(conn, """
        SELECT v.entity_id, v.value_text AS v FROM core.attribute_values v JOIN core.attribute_types a ON a.id = v.attribute_type_id
         WHERE v.model_id = :m AND a.code = 'JunctionKind' AND v.entity_id = ANY(:e)""", m=m["_id"], e=[r["_id"] for r in rows])}
    out = {}
    for r in rows:
        look = notation.type_look(r)
        o = {"id": r["id"], "name": r["name"], "display_id": r["display_id"], "deleted": r["is_deleted"], "type": r["type"],
             "type_name": r["type_name"], "domain": r["domain"], "look": look,
             "icon": _data_uri(r["icon_type"], r["icon"]) if r["icon"] is not None else None}
        if r["is_connector"]:
            o["junction"] = "Or" if (kinds.get(r["_id"]) or "").lower() == "or" else "And"
            o["look"] = {"box": notation.JUNCTION_STYLES[o["junction"]], "shape": notation.JUNCTION_STYLES[o["junction"]],
                         "colour": "000000", "junction": True}
        out[r["id"]] = o
    return out


def _relationships(conn, m: dict, ids: list[str], among: bool = True, of: str | None = None) -> list[dict]:
    """Relationships between the given entities (or from/to `of` and any of them), as the reader sees the model."""
    ids = [i for i in ids if repo._as_guid(i)]
    if not ids:
        return []
    where = ("s.guid = ANY(CAST(:ids AS uuid[])) AND t.guid = ANY(CAST(:ids AS uuid[]))" if among else
             "((s.guid = CAST(:of AS uuid) AND t.guid = ANY(CAST(:ids AS uuid[]))) OR "
             "(t.guid = CAST(:of AS uuid) AND s.guid = ANY(CAST(:ids AS uuid[]))))")
    return _rows(conn, f"""SELECT r.guid::text AS id, rt.code AS type, rt.name AS type_name, s.guid::text AS source,
                                  t.guid::text AS target, coalesce(r.name, '') AS name
                             FROM core.relationships r JOIN core.relationship_types rt ON rt.id = r.relationship_type_id
                             JOIN core.entities s ON s.id = r.source_entity_id JOIN core.entities t ON t.id = r.target_entity_id
                            WHERE r.model_id = :m AND NOT r.is_deleted AND {where}""", m=m["_id"], ids=ids, of=of)


def _with_pending(conn, m: dict, user, fn):
    """fn(conn) committed, and as the person sees it (their uncommitted changes on top): (committed, theirs)."""
    from . import commits as cm
    committed = fn(conn)
    if not user:
        return committed, committed
    return committed, cm.overlay(conn, m["id"], user.username, fn)


def resync(conn, model: Any, user, view: Any = None, xml: str | None = None) -> dict:
    """What is current for the objects on a view (D354 rule 9): each entity's name, type, look and icon (deleted ones
    marked), and every relationship among them (committed, or the person's uncommitted ones), with what the view
    has that the model no longer has."""
    m = repo.get_model(conn, model)
    if xml is None:
        xml = _view_xml(m, view)
    parsed = parse(xml)
    ids = parsed["entities"]
    ents = _entities(conn, m, ids)
    committed, theirs = _with_pending(conn, m, user, lambda c: _relationships(c, m, ids))
    done = {r["id"] for r in committed}
    rels = [dict(r, committed=r["id"] in done) for r in theirs]
    known = {r["id"] for r in rels}
    on_view = [r for r in parsed["relationships"] if r["id"]]
    hidden = {h.get("id") for h in parsed["hidden"]}
    unseen = [r["id"] for r in on_view if r["id"] not in known]
    # someone else's uncommitted relationship: not gone, only not theirs to see yet (drawn as it was, D354)
    others = {r["g"] for r in _rows(conn, """SELECT target::text AS g FROM core.pending_changes
                                              WHERE model_id = :m AND status = 'pending' AND target_kind = 'relationship'
                                                AND target::text = ANY(:ids)""", m=m["_id"], ids=unseen)} if unseen else set()
    return {"entities": ents, "missing_entities": [i for i in ids if i not in ents],
            "deleted_entities": [i for i, e in ents.items() if e["deleted"]],
            "relationships": rels,
            "new_relationships": [r for r in rels if r["id"] not in {x["id"] for x in on_view} and r["id"] not in hidden],
            "gone_relationships": [i for i in unseen if i not in others],
            "others_uncommitted": sorted(others),
            "model_changed_since": None}


def relationships_of(conn, model: Any, user, entity: str, others: list[str]) -> dict:
    """When an entity is placed: its relationships with the objects already on the view (drawn automatically, D354 rule 5)."""
    m = repo.get_model(conn, model)
    committed, theirs = _with_pending(conn, m, user, lambda c: _relationships(c, m, others, among=False, of=entity))
    done = {r["id"] for r in committed}
    ent = _entities(conn, m, [entity]).get(entity)
    if not ent:
        raise repo.NotFound("No such entity in this model.")
    return {"entity": ent, "relationships": [dict(r, committed=r["id"] in done) for r in theirs]}


def allowed_between(conn, model: Any, source: str, target: str) -> dict:
    """The relationship types the metamodel allows from one entity (or type) to another, with multiplicity; through a
    junction, the types its rules leave (D397)."""
    from . import junctions
    m = repo.get_model(conn, model)

    def type_of(x: str) -> dict:
        g = repo._as_guid(x)
        if g:
            r = _one(conn, """SELECT e.id AS _e, t.id, t.code, t.name, t.is_connector FROM core.entities e
                               JOIN core.entity_types t ON t.id = e.entity_type_id WHERE e.guid = :g AND e.model_id = :m""",
                     g=g, m=m["_id"])
            if r:
                return r
        t = repo._find_type(conn, m["_id"], x)
        return {"_e": None, "id": t["_id"], "code": t["code"], "name": t["name"], "is_connector": t.get("is_connector")}
    s, t = type_of(source), type_of(target)
    rows = _rows(conn, """SELECT rt.code, rt.name, rt.verb, a.source_multiplicity, a.target_multiplicity, a.note
                            FROM core.allowed_relationships a JOIN core.relationship_types rt ON rt.id = a.relationship_type_id
                           WHERE a.source_type_id = :s AND a.target_type_id = :t AND NOT a.is_deleted ORDER BY rt.sort_order""",
                 s=s["id"], t=t["id"])
    out = []
    for r in rows:
        why = None
        if s["is_connector"] or t["is_connector"]:
            r["source_multiplicity"] = r["target_multiplicity"] = ""     # none at a junction's end (D397)
            if s["_e"] and t["_e"]:
                rt = _one(conn, "SELECT id AS _id, name FROM core.relationship_types WHERE model_id = :m AND code = :c",
                          m=m["_id"], c=r["code"])
                sp = conn.begin_nested()
                try:
                    junctions.check(conn, s["_e"], t["_e"], rt)
                except EditError as exc:
                    why = str(exc)
                finally:
                    sp.rollback()
        if not why:
            out.append(r)
    return {"source_type": s["code"], "target_type": t["code"], "allowed": out}


# ---------------------------------------------------------------- a view built in Python (MCP, samples, copies)

BANDS = ["Motivation", "Strategy", "Business", "Common", "Application", "Technology", "Implementation & Migration",
         "Implementation and Migration", "Data", "Governance"]
W, H, GAP, PER_ROW = 160, 70, 40, 6
# the stencil's domains, as the owner's ArchiMate 4 guide lists them, and a TOGAF-metamodel model's; any other after,
# alphabetically (owner, 10 Nov 2026, D412). Within a domain, the metamodel's own order (active structure, behaviour,
# passive structure, then others; EA Explorer's extensions last, marked). The plugin keeps the same list.
STENCIL_DOMAINS = ["Motivation", "Strategy", "Common", "Business", "Data", "Application", "Technology",
                   "Implementation & Migration", "Implementation and Migration", "Governance"]


def stencil_domain_key(domain: str) -> tuple:
    return (STENCIL_DOMAINS.index(domain), "") if domain in STENCIL_DOMAINS else (len(STENCIL_DOMAINS), (domain or "").lower())


def setup(conn, model: Any, user, view: Any = None) -> dict:
    """The plugin's setup message (docs/phase-28.md): the model's types with their looks, the allowed relationships, the
    relationship types' lines, whether the person may only read, and the own icons of the entities on the view."""
    m = repo.get_model(conn, model)
    types = {}
    rows = _rows(conn, """SELECT t.code, t.name, t.notation, t.fill_colour, t.is_connector, t.description, t.sort_order,
                                 l.name AS domain, l.colour AS domain_colour
                            FROM core.entity_types t JOIN core.layers l ON l.id = t.layer_id
                           WHERE t.model_id = :m AND NOT t.is_deleted""", m=m["_id"])
    for r in sorted(rows, key=lambda r: (stencil_domain_key(r["domain"]), r["sort_order"] or 0, r["name"])):
        if r["is_connector"]:
            continue                  # the plugin offers the two junctions itself
        lk = notation.type_look(r)
        types[r["code"]] = {"name": r["name"], "domain": r["domain"], "colour": lk["colour"], "box": lk["box"], "shape": lk["shape"]}
        if (r.get("description") or "").startswith("EA Explorer extension"):
            types[r["code"]]["extension"] = True      # marked in the stencil (D345)
    # source, relationship, target, and each end's multiplicity (D395) for the Allowed relationships tab (D420)
    allowed = [[r["s"], r["r"], r["t"], r["sm"] or "", r["tm"] or ""] for r in _rows(conn, """
        SELECT s.code AS s, rt.code AS r, t.code AS t, a.source_multiplicity AS sm, a.target_multiplicity AS tm
          FROM core.allowed_relationships a
          JOIN core.entity_types s ON s.id = a.source_type_id JOIN core.entity_types t ON t.id = a.target_type_id
          JOIN core.relationship_types rt ON rt.id = a.relationship_type_id
         WHERE a.model_id = :m AND NOT a.is_deleted AND NOT s.is_connector AND NOT t.is_connector
         ORDER BY 1, 2, 3""", m=m["_id"])]
    rel_types = {r["code"]: {"name": r["name"], "style": notation.line(r["code"])} for r in _rows(conn, """
        SELECT code, name FROM core.relationship_types WHERE model_id = :m AND NOT is_deleted ORDER BY sort_order, name""", m=m["_id"])}
    read_only = False
    try:
        _writable(m)
        if user is not None:
            may_draw(conn, user, m)
    except EditError:
        read_only = True
    icons = {}
    if view:
        try:
            ids = parse(_view_xml(m, view))["entities"]
        except EditError:
            ids = []
        icons = {e["id"]: e["icon"] for e in _entities(conn, m, ids).values() if e.get("icon")}
    domains = sorted({t["domain"] for t in types.values()}, key=stencil_domain_key)
    return {"eax": "setup", "types": types, "domains": domains, "allowed": allowed, "relationshipTypes": rel_types,
            "readOnly": read_only, "entityIcons": icons}


def layout(entities: list[dict]) -> dict[str, tuple[int, int]]:
    """Domain bands top-down, as an ArchiMate layered view: motivation and strategy first, then business, application,
    technology, implementation and migration; a grid within each band."""
    order = {d: i for i, d in enumerate(BANDS)}
    bands: dict[str, list[dict]] = {}
    for e in entities:
        bands.setdefault(e.get("domain") or "", []).append(e)
    pos, y = {}, 40
    for d in sorted(bands, key=lambda d: (order.get(d, 99), d)):
        for i, e in enumerate(bands[d]):
            pos[e["id"]] = (40 + (i % PER_ROW) * (W + GAP), y + (i // PER_ROW) * (H + GAP))
        y += ((len(bands[d]) - 1) // PER_ROW + 1) * (H + GAP) + GAP
    return pos


def _attr(**kv) -> str:
    return " ".join(f"{k}={quoteattr(str(v))}" for k, v in kv.items() if v is not None)


def build_xml(entities: list[dict], relationships: list[dict], placeholders: list[dict] | None = None,
              hidden: list[dict] | None = None, positions: dict | None = None) -> str:
    """A draw.io file: entities [{id, name, type, domain, look{box,colour}, icon?, junction?}], relationships
    [{id, type, source, target, committed?}], placeholders [{type, name, look}], hidden [{rel, id, source, target}]."""
    pos = positions or layout(entities)
    root_attrs = _attr(id="0", label="", ea_hidden=json.dumps(hidden) if hidden else None)
    cells = [f"<object {root_attrs}><mxCell/></object>", '<mxCell id="1" parent="0"/>']
    cell_of = {}
    for n, e in enumerate(entities, 2):
        cid = f"e{n}"
        cell_of[e["id"]] = cid
        x, y = pos.get(e["id"], (40, 40))
        style = (e.get("look") or {}).get("box") or notation.look("", "").get("box")
        w, h = (W, H)
        if e.get("junction"):
            w = h = 14
            style = notation.JUNCTION_STYLES.get(e["junction"], notation.JUNCTION_STYLES["And"])
        if e.get("icon"):
            style += f"image={e['icon']};imageWidth=18;imageHeight=18;imageAlign=right;imageVerticalAlign=top;"
        if e.get("junction"):          # as the plugin draws one (docs/phase-28.md, the cells)
            a = _attr(id=cid, label="", ea_junction=e["id"], ea_junction_kind=e["junction"].lower())
        else:
            a = _attr(id=cid, label=e["name"], ea_id=e["id"], ea_type=e["type"])
        cells.append(f'<object {a}><mxCell style={quoteattr(style)} vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell></object>')
    y0 = max([p[1] for p in pos.values()] + [0]) + H + 2 * GAP
    for n, p in enumerate(placeholders or [], 1):
        style = (p.get("look") or {}).get("box", "") + "dashed=1;fontStyle=2;opacity=70;"
        a = _attr(id=f"p{n}", label=p.get("name") or p["type"], ea_type=p["type"], ea_placeholder="1")
        cells.append(f'<object {a}><mxCell style={quoteattr(style)} vertex="1" parent="1">'
                     f'<mxGeometry x="{40 + (n - 1) * (W + GAP)}" y="{y0}" width="{W}" height="{H}" as="geometry"/></mxCell></object>')
    hidden_ids = {h.get("id") for h in hidden or []}
    for n, r in enumerate(relationships, 1):
        if r["id"] in hidden_ids or r["source"] not in cell_of or r["target"] not in cell_of:
            continue
        style = notation.line(r["type"]) + ("" if r.get("committed", True) else "dashed=1;")
        # a relationship's name is its line's label (D412); no name, no label
        a = _attr(id=f"r{n}", label=r.get("name") or "", ea_rel=r["type"], ea_rel_id=r["id"],
                  ea_uncommitted=None if r.get("committed", True) else "1")
        cells.append(f'<object {a}><mxCell style={quoteattr(style)} edge="1" parent="1" source="{cell_of[r["source"]]}" '
                     f'target="{cell_of[r["target"]]}"><mxGeometry relative="1" as="geometry"/></mxCell></object>')
    return ('<mxfile host="EA Explorer"><diagram id="view" name="View"><mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" '
            'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169" pageHeight="827">'
            "<root>" + "".join(cells) + "</root></mxGraphModel></diagram></mxfile>")


def generate(conn, model: Any, user, entity_ids: list[str], include_relationships: bool = True) -> str:
    """The xml of a view of the given entities (as the person sees them), laid out by domain."""
    m = repo.get_model(conn, model)
    ents = _entities(conn, m, entity_ids)
    missing = [i for i in entity_ids if i not in ents]
    if missing:
        raise EditError(f"{len(missing)} of the entities are not in {m['name']}: {', '.join(missing[:3])}")
    rels = []
    if include_relationships:
        committed, theirs = _with_pending(conn, m, user, lambda c: _relationships(c, m, list(ents)))
        done = {r["id"] for r in committed}
        rels = [dict(r, committed=r["id"] in done) for r in theirs]
    return build_xml([e for e in ents.values() if not e["deleted"]], rels)


def create_from_entities(conn, model: Any, user, name: str, entities: list[str], include_relationships: bool = True,
                         description: str = "") -> dict:
    """MCP (D354): a drawn view of chosen entities, laid out automatically, saved as the person."""
    resolved = []
    m = repo.get_model(conn, model)
    for e in entities:
        g = repo._as_guid(e)
        if g:
            resolved.append(str(g))
            continue
        r = _one(conn, """SELECT guid::text AS id FROM core.entities WHERE model_id = :m AND NOT is_deleted
                           AND (lower(name) = lower(:e) OR lower(display_id) = lower(:e)) LIMIT 1""", m=m["_id"], e=str(e))
        if not r:
            raise EditError(f"No entity {e!r} in {m['name']}.")
        resolved.append(r["id"])
    xml = generate(conn, model, user, resolved, include_relationships)
    from . import views_client as vc
    try:
        return vc.create(m["id"], {"name": name, "description": description, "xml": xml, "source": "mcp",
                                   "source_note": f"{len(resolved)} entities"}, user.username, access(conn, model, user)["marker"])
    except vc.ViewsDown as exc:
        raise EditError(f"The drawn view was not made: {exc}", exc.status if exc.status in (400, 403, 404, 409) else 503) from exc


# ---------------------------------------------------------------- copies for a copied or child model, and merges

def maps(conn, src_id: int, dst_id: int) -> tuple[dict[str, str], dict[str, str]]:
    """Which of src's entities and relationships are which of dst's (by origin): the views of a copy, a child or a merge
    are bound to dst's own (D354); an entity dst does not have becomes a placeholder (the views service rebinds)."""
    ent_map = {r["s"]: r["d"] for r in _rows(conn, """SELECT s.guid::text AS s, d.guid::text AS d FROM core.entities d
                                                     JOIN core.entities s ON (d.origin_guid = s.guid OR s.origin_guid = d.guid
                                                                              OR d.guid = s.guid)
                                                    WHERE s.model_id = :s AND d.model_id = :d""", s=src_id, d=dst_id)}
    rel_map = {r["s"]: r["d"] for r in _rows(conn, """SELECT s.guid::text AS s, d.guid::text AS d FROM core.relationships d
                                                     JOIN core.relationships s ON (d.origin_guid = s.guid OR s.origin_guid = d.guid)
                                                    WHERE s.model_id = :s AND d.model_id = :d""", s=src_id, d=dst_id)}
    return ent_map, rel_map


def copy_views(conn, src_id: int, dst_id: int, source: str = "model-copy", only_new: bool = False, actor: str = "system") -> dict:
    """The views of src as views of dst (the views service), bound to dst's own entities; only_new: a merge brings
    across the views dst does not have (by name). Never fails the copy or merge: says what was left out."""
    from . import views_client as vc
    guids = {r["id"]: r["g"] for r in _rows(conn, "SELECT id, guid::text AS g FROM core.models WHERE id IN (:s, :d)", s=src_id, d=dst_id)}
    ent_map, rel_map = maps(conn, src_id, dst_id)
    try:
        return vc.copy_model(guids[src_id], guids[dst_id], actor, ent_map, rel_map, only_new=only_new, source=source)
    except vc.ViewsDown as exc:
        return {"drawn_views": 0, "own_views": 0, "note": f"Drawn views were not copied: {exc}"}


# ---------------------------------------------------------------- entities' own icons (part 2)

_SVG_BAD_TAGS = {"script", "foreignobject", "iframe", "object", "embed", "audio", "video", "canvas", "handler", "listener",
                 "set", "animate", "animatemotion", "animatetransform", "a", "image", "feimage", "use", "style"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def check_icon(content: bytes, file_name: str = "", content_type: str = "") -> str:
    """The content type of a safe icon (image/svg+xml or image/png), else EditError. SVG is refused, not cleaned, when it
    holds anything that could run or fetch: scripts, foreign objects, event attributes, links, styles, external refs."""
    if not content:
        raise EditError("Choose an icon file (SVG or PNG).")
    if len(content) > MAX_ICON:
        raise EditError(f"An icon is at most {MAX_ICON // 1024} KB (this one is {len(content) // 1024} KB).", 413)
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    name = (file_name or "").lower()
    if not (name.endswith(".svg") or "svg" in (content_type or "") or content.lstrip()[:5] in (b"<svg ", b"<?xml", b"<svg>")):
        raise EditError("An icon is an SVG or PNG file.")
    try:
        root = SafeET.fromstring(content)
    except Exception as exc:  # noqa: BLE001  (defusedxml refuses entities and DTD tricks)
        raise EditError("This SVG cannot be read safely.") from exc
    if _local(root.tag) != "svg":
        raise EditError("This is not an SVG image.")
    for el in root.iter():
        if _local(el.tag) in _SVG_BAD_TAGS:
            raise EditError(f"The SVG holds <{_local(el.tag)}>, which an icon may not (scripts, links, styles and embedded "
                            "content are refused).")
        for k, v in el.attrib.items():
            lk, lv = _local(k), str(v).strip().lower()
            if lk.startswith("on") or lk in ("href", "src", "style") or "javascript:" in lv or "url(" in lv or "data:" in lv:
                raise EditError(f"The SVG has an attribute {_local(k)!r} that an icon may not have (events, links, styles, urls).")
    return "image/svg+xml"


def _blob(v: Any) -> bytes:
    """bytea as bytes (a driver gives bytes or memoryview; a text form '\\x..' is read as hex)."""
    if isinstance(v, str):
        return bytes.fromhex(v[2:]) if v.startswith("\\x") else v.encode()
    return bytes(v)


def _data_uri(content_type: str | None, content: bytes | None) -> str | None:
    if not content:
        return None
    return f"data:{content_type};base64,{base64.b64encode(_blob(content)).decode('ascii')}"


def _entity_row(conn, m: dict, entity: Any) -> dict:
    g = repo._as_guid(entity)
    r = _one(conn, "SELECT id, guid, name FROM core.entities WHERE model_id = :m AND NOT is_deleted AND "
                   + ("guid = :e" if g else "lower(display_id) = lower(:e)"), m=m["_id"], e=str(g or entity))
    if not r:
        raise repo.NotFound(f"No entity {entity!r} in {m['name']}.")
    return r


def set_icon(conn, model: Any, user, entity: Any, content: bytes, file_name: str = "", content_type: str = "") -> dict:
    m = repo.get_model(conn, model)
    _writable(m)
    e = _entity_row(conn, m, entity)
    ctype = check_icon(content, file_name, content_type)
    conn.execute(text("""INSERT INTO core.entity_icons (entity_id, content_type, content, uploaded_by) VALUES (:e, :t, :c, :u)
                         ON CONFLICT (entity_id) DO UPDATE SET content_type = EXCLUDED.content_type, content = EXCLUDED.content,
                                                               uploaded_by = EXCLUDED.uploaded_by, uploaded_at = now()"""),
                 {"e": e["id"], "t": ctype, "c": content, "u": user.username})
    return {"entity": str(e["guid"]), "content_type": ctype, "message": f"{e['name']} has its own icon now."}


def remove_icon(conn, model: Any, user, entity: Any) -> dict:
    m = repo.get_model(conn, model)
    _writable(m)
    e = _entity_row(conn, m, entity)
    conn.execute(text("DELETE FROM core.entity_icons WHERE entity_id = :e"), {"e": e["id"]})
    return {"entity": str(e["guid"]), "message": f"{e['name']} shows its type's icon again."}


def get_icon(conn, model: Any, entity: Any) -> tuple[str, bytes] | None:
    m = repo.get_model(conn, model)
    e = _entity_row(conn, m, entity)
    r = _one(conn, "SELECT content_type, content FROM core.entity_icons WHERE entity_id = :e", e=e["id"])
    return (r["content_type"], _blob(r["content"])) if r else None


# ---------------------------------------------------------------- heat maps (part 2)

PALETTE = ["2E7D32", "9CCC65", "FDD835", "FB8C00", "C62828", "6A1B9A", "1565C0", "00838F", "5D4037", "546E7A"]
SCALE = ["2E7D32", "9CCC65", "FDD835", "FB8C00", "C62828"]       # low to high


def bands(lo: float, hi: float, n: int = 5) -> list[tuple[float, float]]:
    if hi <= lo:
        return [(lo, hi)]
    step = (hi - lo) / n
    return [(round(lo + i * step, 6), round(lo + (i + 1) * step, 6)) for i in range(n)]


def _num(x: float) -> str:
    """12,500 or 2.6: a number for a legend."""
    return f"{int(x):,}" if float(x).is_integer() else f"{x:,.6g}"


def heat_map(conn, model: Any, attribute: str, ranges: list | None = None, entities: list[str] | None = None) -> dict:
    """Each entity's value of one attribute (a pick list or a number) and its colour, with the legend (D354)."""
    m = repo.get_model(conn, model)
    a = _one(conn, """SELECT a.id, a.code, a.name, a.data_type_code AS dt, a.pick_list_id FROM core.attribute_types a
                       WHERE a.model_id = :m AND NOT a.is_deleted AND lower(:a) IN (lower(a.code), lower(a.name))""",
             m=m["_id"], a=attribute)
    if not a:
        raise repo.NotFound(f"No attribute {attribute!r} in {m['name']}.")
    where = " AND e.guid = ANY(CAST(:ids AS uuid[]))" if entities else ""
    vals = _rows(conn, f"""SELECT e.guid::text AS id, v.value_text, v.value_number FROM core.attribute_values v
                             JOIN core.entities e ON e.id = v.entity_id
                            WHERE v.model_id = :m AND v.attribute_type_id = :a AND NOT e.is_deleted{where}""",
                 m=m["_id"], a=a["id"], ids=[i for i in entities or [] if repo._as_guid(i)])
    legend, colours, values = [], {}, {}
    dt = (a["dt"] or "").lower()
    if not a["pick_list_id"] and dt not in ("list", "text", "number", "integer", "decimal", "currency", "percent"):
        raise EditError(f"A heat map colours by a pick list, text or a number; {a['name']} is {dt or 'neither'}.")
    if a["pick_list_id"] or dt in ("list", "text"):
        choices = [r["value"] for r in _rows(conn, """SELECT value FROM core.pick_list_values WHERE pick_list_id = :p
                                                       AND NOT is_deleted ORDER BY sort_order""", p=a["pick_list_id"])] \
            if a["pick_list_id"] else sorted({v["value_text"] for v in vals if v["value_text"]})
        pal = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(choices)}
        legend = [{"label": c, "colour": pal[c]} for c in choices]
        for v in vals:
            if v["value_text"] in pal:
                colours[v["id"]], values[v["id"]] = pal[v["value_text"]], v["value_text"]
    else:
        nums = [float(v["value_number"]) for v in vals if v["value_number"] is not None]
        if ranges:
            rs = [(float(r[0]), float(r[1])) for r in ranges]
        else:
            rs = bands(min(nums), max(nums)) if nums else []
        scale = SCALE if len(rs) <= len(SCALE) else (SCALE * (len(rs) // len(SCALE) + 1))
        legend = [{"label": f"{_num(lo)} to {_num(hi)}", "from": lo, "to": hi, "colour": scale[i]} for i, (lo, hi) in enumerate(rs)]
        for v in vals:
            if v["value_number"] is None:
                continue
            x = float(v["value_number"])
            for i, (lo, hi) in enumerate(rs):
                if lo <= x <= hi if i == len(rs) - 1 else lo <= x < hi:
                    colours[v["id"]], values[v["id"]] = scale[i], x
                    break
    return {"attribute": {"code": a["code"], "name": a["name"], "data_type": a["dt"]}, "legend": legend,
            "colours": colours, "values": values, "no_value": "EEEEEE"}


# ---------------------------------------------------------------- a drawn view as project evidence (part 2)

def add_evidence(conn, project: Any, user, data: dict) -> dict:
    """A drawn view as a deliverable's artifact (item) or a key question's answer (question): a link only (D408), to the
    live view or one version of it (read only); no picture of it is stored. conn is the projects' connection; the
    model is read on the repository's beside it, the view in the views service, both kept by guid (D266, D405)."""
    from . import projects as pj
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    cc = pj.core(conn)
    model = repo.get_model(cc, data.get("model") or "")
    from . import views_client as vc
    asked = int(data["version"]) if data.get("version") else None
    try:
        found = vc.get_view(model["id"], data.get("view") or "", asked, with_xml=False)
    except vc.ViewsDown as exc:
        raise EditError(f"The drawn view cannot be read: {exc}", 404 if exc.status == 404 else 503) from exc
    v = {"name": found["name"], "guid": found["id"]}
    item = qid = None
    if data.get("item"):
        item = _one(conn, "SELECT id, guid FROM proj.items WHERE project_id = :p AND guid::text = :i", p=p["id"], i=str(data["item"]))
        if not item:
            raise EditError("No such deliverable in this project.", 404)
    if data.get("question"):
        q = _one(conn, "SELECT id FROM proj.key_questions WHERE project_id = :p AND (id::text = :q OR guid::text = :q)",
                 p=p["id"], q=str(data["question"]))
        if not q:
            raise EditError("No such key question in this project.", 404)
        qid = q["id"]
    if bool(item) == bool(qid):
        raise EditError("Point the view at one deliverable (item) or one key question.")
    ev = _one(conn, """INSERT INTO proj.view_evidence (project_id, item_id, question_id, model_guid, view_guid, version_no, note, added_by)
                       VALUES (:p, :i, :q, :m, :v, :n, :note, :u) RETURNING guid::text AS id""",
              p=p["id"], i=item["id"] if item else None, q=qid, m=str(model["id"]), v=str(v["guid"]), n=asked,
              note=(data.get("note") or "")[:500], u=user.username)
    which = f"version {asked}" if asked else "the live view"
    if qid:     # the answer links to the view (a page of EA Explorer)
        link = f"#/metamodel/{model['id']}/drawn-views/{v['guid']}" + (f"?version={asked}" if asked else "")
        n = conn.execute(text("SELECT coalesce(max(sort_order), 0) + 1 FROM proj.question_links WHERE question_id = :q"),
                         {"q": qid}).scalar()
        conn.execute(text("""INSERT INTO proj.question_links (question_id, document_id, url, label, sort_order, added_by)
                             VALUES (:q, NULL, :l, :b, :s, :u)"""),
                     {"q": qid, "l": link, "b": f"Drawn view: {v['name']}" + (f" (v{asked})" if asked else ""), "s": n,
                      "u": user.username})
    return {"id": ev["id"], "message": f"{v['name']} ({which}) is evidence now."}


def evidence(conn, project: Any, user) -> dict:
    """The project's drawn views as evidence; the views' names are read on the repository's connection (D266)."""
    from . import projects as pj
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "read")
    rows = _rows(conn, """SELECT ev.guid::text AS id, i.guid::text AS item, i.name AS item_name, q.guid::text AS question,
                                 q.question AS question_text, ev.model_guid::text AS model, ev.view_guid::text AS view,
                                 ev.version_no AS version, ev.note, ev.added_by, ev.added_at
                            FROM proj.view_evidence ev
                            LEFT JOIN proj.items i ON i.id = ev.item_id
                            LEFT JOIN proj.key_questions q ON q.id = ev.question_id
                           WHERE ev.project_id = :p ORDER BY ev.added_at DESC""", p=p["id"])
    views = {}
    if rows:          # the views' names from the views service, the models' from the repository (D266, D405)
        from . import views_client as vc
        names = {r["id"]: r["name"] for r in _rows(pj.core(conn), "SELECT guid::text AS id, name FROM core.models WHERE guid::text = ANY(:g)",
                                                   g=sorted({r["model"] for r in rows}))}
        for mg in sorted({r["model"] for r in rows}):
            try:
                for v in vc.list_views(mg).get("views") or []:
                    views[v["id"]] = {"view_name": v["name"], "is_deleted": False, "model_name": names.get(mg)}
            except vc.ViewsDown:
                pass
    for r in rows:
        r["added_at"] = _ts(r["added_at"])
        found = views.get(r["view"]) or {}
        r["view_name"], r["model_name"] = found.get("view_name"), found.get("model_name")
        r["view_removed"] = bool(found.get("is_deleted")) or not found
        r["link"] = f"#/metamodel/{r['model']}/drawn-views/{r['view']}" + (f"?version={r['version']}" if r["version"] else "")
    return {"evidence": rows}


def remove_evidence(conn, project: Any, user, evidence_id: str) -> dict:
    from . import projects as pj
    p = pj.project_row(conn, project)
    pj._need(conn, p, user, "contribute")
    n = conn.execute(text("DELETE FROM proj.view_evidence WHERE project_id = :p AND guid::text = :e"),
                     {"p": p["id"], "e": evidence_id}).rowcount
    if not n:
        raise EditError("No such evidence in this project.", 404)
    return {"message": "The view is no longer evidence."}


def view_pending(conn, model: Any, user, targets: list) -> dict:
    """The person's uncommitted changes to the relationships and junctions on one drawn view (owner, 10 Nov 2026, D412):
    what the view's Commit button commits (or asks the model's committers to commit), and nothing else of theirs."""
    from . import commits as cm
    m = repo.get_model(conn, model)
    want = {str(repo._as_guid(t)) for t in (targets or []) if repo._as_guid(t)}
    rows = _rows(conn, """SELECT c.guid::text AS id, c.label, c.target::text AS target, c.target_kind, c.op
                            FROM core.pending_changes c
                           WHERE c.model_id = :m AND c.author = :a AND c.status = 'pending' ORDER BY c.id""",
                 m=m["_id"], a=user.username.lower()) if want else []
    mine = [r for r in rows if r["target"] in want]
    cm_m = cm._model(conn, model)
    return {"changes": mine, "count": len(mine), "uses_commits": cm.uses_commits(cm_m), "may_commit": cm.may_commit(conn, user, cm_m)}



# ---------------------------------------------------------------- two-way sync (owner, 10 Nov 2026, D413)
DRAWN_OPS = ("relationship.create", "relationship.delete", "relationship.rename", "entity.create", "entity.update")
DRAWN_MESSAGES = {"relationship.create": "Drawn on view", "relationship.rename": "Renamed on drawn view",
                  "relationship.delete": "Deleted on drawn view", "entity.create": "Created on drawn view",
                  "entity.update": "Changed on drawn view"}


def default_message(op: str, view_name: str = "") -> str:
    return f"{DRAWN_MESSAGES.get(op, 'Changed on drawn view')} {(view_name or '').strip()}".strip()


def change_now(conn, model: Any, user, op: str, args: dict, view_name: str = "", message: str = "") -> dict:
    """One change made on a drawn view, in the model at once and committed as the person (D413):

    * relationships (drawn, renamed, deleted from the model) and junctions: anyone who may change the model;
    * entities (edited, or made from a placeholder): the model's committers only, so a view never holds an entity the
      model will not have.

    Checked exactly as a save (allowed types, junction rules, required attributes); never outside the metamodel here.
    A library model being built has no commits: the change is saved straight away."""
    from . import commits as cm
    if op not in DRAWN_OPS:
        raise EditError(f"A drawn view does not make the change {op!r}.", 400)
    m = cm._model(conn, model)
    args = json.loads(json.dumps(args or {}, default=str))
    if op == "relationship.create":
        args.setdefault("data", {})["allow_outside"] = False
    if not cm.drawn_free(conn, m, op, args) and not cm.may_commit(conn, user, m):
        raise EditError("Only the model's committers make or change entities on a drawn view. Realise the placeholder with "
                        "an entity that exists, or ask a committer.", 403)
    msg = (message or "").strip() or default_message(op, view_name)
    answer = "entity" if op.startswith("entity.") else "result"
    if not cm.uses_commits(m):
        args = cm._resolve_refs(conn, m, op, cm._prepare(op, args))
        out = cm._apply(conn, m, op, args, user.username)
        if answer == "entity" and isinstance(out, dict) and out.get("id"):
            out = repo.get_entity_detail(conn, str(m["id"]), str(out["id"]))
        out = dict(out) if isinstance(out, dict) else {"result": out}
        out.update(pending=False, committed=True, commit=None, message=msg)
        return out
    rec = cm.record(conn, m["id"], user.username, op, args, answer)
    done = cm.commit(conn, m["id"], user, change_ids=[rec["change"]], message=msg, relationships_only=True)
    out = {k: v for k, v in rec.items() if k != "note"}
    out.update(pending=False, committed=True, commit=done["commit"], number=done["number"], message=msg)
    return out


def commit_mine(conn, model: Any, user, change_ids: list | None, message: str = "") -> dict:
    """The editor's Uncommitted changes panel (D413): commits the person's chosen changes (all when none are given).
    Relationships and junctions anyone who may change the model commits; anything else needs a committer."""
    from . import commits as cm
    return cm.commit(conn, model, user, change_ids=change_ids or None, message=message, relationships_only=True)
