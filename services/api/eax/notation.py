"""How an entity type looks on a drawn view (phase 28, D354, D396, D398): the ArchiMate 4 notation.

Every entity type has a notation: the ArchiMate element whose shape and icon it shows (core.entity_types.notation).
This module turns it into draw.io styles, reusing draw.io's own ArchiMate drawings (mxgraph.archimate3, Apache 2.0,
already in our draw.io image) for the glyphs only: the names, domains and colours are ArchiMate 4's (D392).

* box: the rectangle with the small icon in its corner (the default on a view);
* shape: the icon's own outline (a person may switch one object to it, D398);
* colour: the type's own fill colour, else its domain's (D392).
Our extensions and anything without an ArchiMate glyph show as a plain rounded box (specialisations show
<<Type>> above the name, which the web adds). Relationship lines follow the ArchiMate notation.
"""

from __future__ import annotations

import re

_BASE = "html=1;outlineConnect=0;whiteSpace=wrap;"
_BOX = _BASE + "shape=mxgraph.archimate3.application;"

# element -> (appType, archiType or "", shape-form style suffix or "")
ELEMENTS: dict[str, tuple[str, str, str]] = {
    "Role": ("role", "square", "role;"),
    "Collaboration": ("collab", "square", "collaboration;"),
    "Path": ("path", "square", "path;strokeWidth=6;"),
    "Service": ("serv", "rounded", "service;"),
    "Process": ("proc", "rounded", "process;"),
    "Function": ("func", "rounded", "function;"),
    "Event": ("event", "rounded", "event;"),
    "Grouping": ("grouping", "square", "grouping;"),
    "Location": ("location", "square", "locationIcon;aspect=fixed;"),
    "BusinessActor": ("actor", "square", "actor;verticalLabelPosition=bottom;verticalAlign=top;align=center;"),
    "BusinessInterface": ("interface", "square", "interface;"),
    "BusinessObject": ("passive", "square", "businessObject;overflow=fill;"),
    "Product": ("product", "square", "product;"),
    "ApplicationComponent": ("comp", "square", "component;"),
    "ApplicationInterface": ("interface", "square", "interface;"),
    "DataObject": ("passive", "square", "businessObject;overflow=fill;"),
    "Node": ("node", "square", "node;"),
    "Device": ("device", "", "device;"),
    "SystemSoftware": ("sysSw", "square", "sysSw;"),
    "TechnologyInterface": ("interface", "square", "interface;"),
    "CommunicationNetwork": ("netw", "square", "network;"),
    "DistributionNetwork": ("distribution", "square", "distribution;strokeWidth=4;"),
    "Equipment": ("equipment", "square", "equipment;"),
    "Facility": ("facility", "square", "facility;"),
    "Artifact": ("artifact", "square", ""),
    "Material": ("material", "square", "material;"),
    "Resource": ("resource", "square", "resource;"),
    "Capability": ("capability", "rounded", "capability;"),
    "ValueStream": ("valueStream", "rounded", "valueStream;"),
    "CourseOfAction": ("course", "rounded", "course;"),
    "Stakeholder": ("role", "oct", "role;"),
    "Driver": ("driver", "oct", "driver;"),
    "Assessment": ("assess", "oct", "assess;"),
    "Goal": ("goal", "oct", "goal;"),
    "Outcome": ("outcome", "oct", "outcome;strokeWidth=2;"),
    "Principle": ("principle", "oct", "principle;strokeWidth=2;"),
    "Requirement": ("requirement", "oct", "requirement;"),
    "Meaning": ("meaning", "oct", ""),
    "Value": ("amValue", "oct", ""),
    "WorkPackage": ("workPackage", "rounded", "workPackage;strokeWidth=5;"),
    "Deliverable": ("deliverable", "", "deliverable;"),
    "Plateau": ("plateau", "", "plateau;"),
}
# the junction (D397): a small circle, filled for And, hollow for Or
JUNCTION = "Junction"
JUNCTION_STYLES = {
    "And": "ellipse;html=1;aspect=fixed;fillColor=#000000;strokeColor=#000000;",
    "Or": "ellipse;html=1;aspect=fixed;fillColor=#FFFFFF;strokeColor=#000000;",
}
NOTATIONS = sorted(ELEMENTS) + [JUNCTION]

RELATIONSHIPS: dict[str, str] = {
    "Composition": "html=1;startArrow=diamondThin;startFill=1;startSize=10;endArrow=none;endFill=0;",
    "Aggregation": "html=1;startArrow=diamondThin;startFill=0;startSize=10;endArrow=none;endFill=0;",
    "Assignment": "html=1;endArrow=block;endFill=1;startArrow=oval;startFill=1;",
    "Realization": "html=1;endArrow=block;endFill=0;dashed=1;",
    "Serving": "html=1;endArrow=open;endFill=1;",
    "Access": "html=1;endArrow=open;endFill=0;dashed=1;dashPattern=1 4;",
    "Influence": "html=1;endArrow=open;endFill=0;dashed=1;dashPattern=6 4;",
    "Triggering": "html=1;endArrow=block;endFill=1;",
    "Flow": "html=1;endArrow=block;endFill=1;dashed=1;dashPattern=6 4;",
    "Specialization": "html=1;endArrow=block;endFill=0;",
    "Association": "html=1;endArrow=none;",
}
_LINE = "edgeStyle=elbowEdgeStyle;elbow=vertical;"
DEFAULT_COLOUR = "E4DED2"          # Common's warm grey: a type with no domain colour
_HEX = re.compile(r"^[0-9A-Fa-f]{6}$")


def clean_colour(c: str | None) -> str:
    """'' or RRGGBB (upper case); raises ValueError otherwise."""
    c = (c or "").strip().lstrip("#")
    if not c:
        return ""
    if not _HEX.match(c):
        raise ValueError(f"{c!r} is not a colour: write six hexadecimal digits, e.g. ECD678.")
    return c.upper()


def clean_notation(n: str | None) -> str:
    n = (n or "").strip()
    if n and n not in ELEMENTS and n != JUNCTION:
        raise ValueError(f"{n!r} is not an ArchiMate 4 element: choose one of {', '.join(NOTATIONS)}, or none.")
    return n


def default_notation(code: str) -> str:
    """An ArchiMate 4 type's own notation (its code), or none (a plain box) for anything else."""
    return code if code in ELEMENTS or code == JUNCTION else ""


def look(notation: str | None, colour: str | None) -> dict:
    """{box, shape, colour}: draw.io styles for a type's box and shape forms, in its colour."""
    colour = (colour or DEFAULT_COLOUR).lstrip("#").upper()
    fill = f"fillColor=#{colour};"
    if notation == JUNCTION:
        return {"box": JUNCTION_STYLES["And"], "shape": JUNCTION_STYLES["And"], "colour": "000000", "junction": True}
    el = ELEMENTS.get(notation or "")
    if not el:
        plain = _BASE + "rounded=1;" + fill
        return {"box": plain, "shape": plain, "colour": colour}
    app, arch, shape = el
    box = _BOX + f"appType={app};" + (f"archiType={arch};" if arch else "") + fill
    if notation == "Grouping":
        box += "dashed=1;fillColor=none;"
    shp = (_BASE + "shape=mxgraph.archimate3." + shape + fill) if shape else box
    return {"box": box, "shape": shp, "colour": colour}


def line(relationship_type: str | None) -> str:
    """The draw.io style of a relationship's line (ArchiMate notation); an unknown type: a plain line."""
    return _LINE + RELATIONSHIPS.get(relationship_type or "", "html=1;endArrow=open;")


def type_look(row: dict) -> dict:
    """A type's look from its metamodel row: notation, fill_colour (own) or domain_colour."""
    return look(row.get("notation") or "", row.get("fill_colour") or row.get("domain_colour") or "")
