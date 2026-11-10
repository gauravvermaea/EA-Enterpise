"""Reading and changing draw.io files (phase 28, D354): what a drawn view shows, and the file bound to another model's
entities (a copy, a child, a merge or a package). The file stays as draw.io wrote it; only ea_ attributes are read."""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
import zlib

from defusedxml import ElementTree as SafeET

MAX_XML = 5_000_000           # characters: a drawn view is a picture, not a store
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class Refused(Exception):
    def __init__(self, message: str, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.details = details or {}


def is_guid(x) -> bool:
    return bool(x) and bool(UUID.match(str(x)))


BLANK = ('<mxfile host="EA Explorer"><diagram id="view" name="View"><mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" '
         'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169" pageHeight="827">'
         '<root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel></diagram></mxfile>')


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
                raise Refused("A page of this draw.io file cannot be read.") from exc
    return out


def parse(xml: str) -> dict:
    """What a draw.io file shows: its objects (bound, placeholders, junctions), its relationship lines, the hidden list.
    Raises Refused when it is not a draw.io file."""
    if not xml or not xml.strip():
        raise Refused("The view is empty: no draw.io file was sent.")
    if len(xml) > MAX_XML:
        raise Refused(f"The view is too large ({len(xml) // 1000} k characters; at most {MAX_XML // 1000} k).", 413)
    try:
        root = SafeET.fromstring(xml)
    except Exception as exc:  # noqa: BLE001  (defusedxml refuses entities and the like, too)
        raise Refused("This is not a draw.io file that can be read.") from exc
    if root.tag not in ("mxfile", "mxGraphModel"):
        raise Refused("This is not a draw.io file (no mxfile or mxGraphModel).")
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


def rebind(xml: str, ent_map: dict[str, str], rel_map: dict[str, str]) -> str:
    """The file bound to the other model's entities and relationships; an entity it does not have becomes a placeholder
    (realised later, or removed), so a copy never holds another model's entities (D354)."""
    def sub(attr: str, mapping: dict[str, str]):
        def f(mo):
            return f'{attr}="{mapping.get(mo.group(1), mo.group(1))}"'
        return f

    def ent(mo):
        new = ent_map.get(mo.group(1))
        return f'ea_id="{new}"' if new else 'ea_placeholder="1"'
    xml = re.sub(r'ea_id="([0-9a-fA-F-]{36})"', ent, xml)
    # a junction is an entity of the model too (D397): one the other model does not have is left unbound
    xml = re.sub(r'ea_junction="([0-9a-fA-F-]{36})"', lambda mo: f'ea_junction="{ent_map.get(mo.group(1), "")}"', xml)
    xml = re.sub(r'ea_rel_id="([0-9a-fA-F-]{36})"', sub("ea_rel_id", rel_map), xml)
    xml = re.sub(r'ea_rel_id="([0-9a-fA-F-]{36})"', lambda mo: mo.group(0) if mo.group(1) in rel_map.values() else "", xml)
    for old, new in list(ent_map.items()) + list(rel_map.items()):      # inside the hidden list (JSON, quoted)
        xml = xml.replace(f"&quot;{old}&quot;", f"&quot;{new}&quot;")
    return xml


def summary(parsed: dict) -> dict:
    return {"objects": len(parsed["objects"]), "entities": len(parsed["entities"]), "relationships": len(parsed["relationships"]),
            "uncommitted_relationships": len([r for r in parsed["relationships"] if r["uncommitted"]]),
            "hidden_relationships": len(parsed["hidden"]), "placeholders": parsed["placeholders"]}
