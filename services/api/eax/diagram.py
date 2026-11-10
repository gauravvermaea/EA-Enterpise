"""The metamodel as an ER diagram: choosing the part to show, and writing it as Mermaid.

Pure functions over the data from repository.get_metamodel_diagram, so the REST API, the MCP server
and the tests share one set of rules. The web screen applies the same rules in Metamodel.jsx
(scopeDiagram); keep the two in step.

Rules
  * Relationship types: all except the catch-all ones (GENERIC) unless asked for.
  * Focus on one entity type: that type, every type it may connect to with the chosen relationship
    types (in either direction), and only the links that touch the focused type.
  * Otherwise the chosen domains (all when none are chosen) and the links between their types; with
    include_connected, also the types in other domains those types connect to.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

GENERIC = ("Association", "Specialization")


def _match(value: str, *candidates: Any) -> bool:
    v = str(value).strip().lower()
    return any(v == str(c).strip().lower() for c in candidates if c is not None)


def scope(data: dict, domains: Iterable[str] | None = None, entity_type: str | None = None,
          relationship_types: Iterable[str] | None = None, include_generic: bool = False,
          include_connected: bool = False, **_ignored) -> dict:
    """The part of the diagram to draw. Raises LookupError for an unknown domain, type or relationship type."""
    all_rels = [r["code"] for r in data["relationship_types"]]
    if relationship_types:
        rels = []
        for want in relationship_types:
            found = [r["code"] for r in data["relationship_types"]
                     if _match(want, r["code"], r["name"], r["id"])]
            if not found:
                raise LookupError(f"No relationship type {want!r}. Known: {', '.join(all_rels)}.")
            rels += found
    else:
        rels = [c for c in all_rels if include_generic or c not in GENERIC]
    keep = set(rels)

    types = {str(t["id"]): t for t in data["entity_types"]}
    links = []
    for link in data["links"]:
        codes = [c for c in link["relationship_types"] if c in keep]
        if codes:
            links.append({"source": str(link["source"]), "target": str(link["target"]), "relationship_types": codes})

    if entity_type:
        focus = next((t for t in data["entity_types"]
                      if _match(entity_type, t["id"], t["name"], t["code"], t.get("table_name"))), None)
        if not focus:
            raise LookupError(f"No entity type {entity_type!r} in this model.")
        fid = str(focus["id"])
        links = [x for x in links if fid in (x["source"], x["target"])]
        ids = {fid} | {x["source"] for x in links} | {x["target"] for x in links}
    else:
        chosen = list(domains or [])
        domain_ids = set()
        for want in chosen:
            found = [str(lay["id"]) for lay in data["domains"] if _match(want, lay["id"], lay["code"], lay["name"])]
            if not found:
                raise LookupError(f"No domain {want!r}. Known: {', '.join(lay['name'] for lay in data['domains'])}.")
            domain_ids.update(found)
        inside = {i for i, t in types.items() if not domain_ids or str(t["domain_id"]) in domain_ids}
        if include_connected:
            links = [x for x in links if x["source"] in inside or x["target"] in inside]
            ids = inside | {x["source"] for x in links} | {x["target"] for x in links}
        else:
            links = [x for x in links if x["source"] in inside and x["target"] in inside]
            ids = inside
        focus = None

    return {
        "focus": str(focus["id"]) if focus else None,
        "entity_types": [t for t in data["entity_types"] if str(t["id"]) in ids],
        "links": links,
        "relationship_types": rels,
    }


def _token(text: str) -> str:
    """A Mermaid identifier: letters, digits and underscores only."""
    out = re.sub(r"\W+", "_", str(text)).strip("_")
    return out if out and not out[0].isdigit() else f"x_{out}"


def to_mermaid(part: dict, with_attributes: bool = True) -> str:
    """Mermaid erDiagram text. Links are many-to-many; the label lists the allowed relationship types,
    read from the left entity to the right one."""
    names = {str(t["id"]): _token(t["code"]) for t in part["entity_types"]}
    lines = ["erDiagram"]
    for t in part["entity_types"]:
        label = t["name"].replace('"', "'")
        attrs = (t.get("attributes") or []) if with_attributes else []
        if not attrs:
            lines.append(f'    {names[str(t["id"])]}["{label}"]')
            continue
        lines.append(f'    {names[str(t["id"])]}["{label}"] {{')
        for a in attrs:
            notes = [n for n in ("required" if a.get("is_required") else "", a.get("pick_list") or "",
                                 a.get("unit") or "") if n]
            note = f' "{", ".join(notes)}"' if notes else ""
            lines.append(f'        {_token(a["data_type"])} {_token(a["column_name"])}{note}')
        lines.append("    }")
    for x in part["links"]:
        if x["source"] in names and x["target"] in names:
            lines.append(f'    {names[x["source"]]} }}o--o{{ {names[x["target"]]} : "{", ".join(x["relationship_types"])}"')
    return "\n".join(lines) + "\n"
