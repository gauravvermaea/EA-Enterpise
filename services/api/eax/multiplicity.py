"""Relationship multiplicity (owner, 9 Nov 2026, D395), as in the owner's ArchiMate 4 guide.

An allowed relationship may carry a multiplicity at each of its two ends: how many instances may take part at that end.
Three forms: a single number n (exactly n), ``*`` (0..*, unbounded) and a range n..m (m may be ``*``; m greater than n).
Left empty it constrains nothing. It never makes a relationship allowed; it constrains one already allowed.

Read it as the guide does: the **target end** says how many targets one source has; the **source end** says how many
sources one target has. "A claim belongs to exactly one policy" is a relationship from Claim to Policy with target end 1.
The data quality checks flag every entity that breaks one (a warning; it never blocks a commit).
"""

from __future__ import annotations

import re

_RANGE = re.compile(r"^(\d+)\.\.(\d+|\*)$")


def parse(text: str | None) -> tuple[int, int | None] | None:
    """(lower, upper or None for unbounded), or None when empty. Raises ValueError with the reason."""
    t = "".join(str(text or "").split())
    if not t:
        return None
    if t == "*":
        return (0, None)
    if t.isdigit():
        n = int(t)
        if n < 1:
            raise ValueError("A single number is a positive whole number (use 0..1 or * for optional).")
        return (n, n)
    m = _RANGE.match(t)
    if not m:
        raise ValueError(f"{text!r} is not a multiplicity: write a number (1), * or a range (0..1, 1..*, 2..5).")
    lo, hi = int(m.group(1)), None if m.group(2) == "*" else int(m.group(2))
    if hi is not None and hi <= lo:
        raise ValueError(f"In {text!r} the upper bound must be greater than the lower.")
    return (lo, hi)


def clean(text: str | None) -> str:
    """The multiplicity as kept: '' when empty, else n, * or n..m (checked)."""
    b = parse(text)
    if b is None:
        return ""
    lo, hi = b
    if hi is None:
        return "*" if lo == 0 else f"{lo}..*"
    return str(lo) if lo == hi else f"{lo}..{hi}"


def fits(text: str | None, count: int) -> bool:
    b = parse(text)
    if b is None:
        return True
    lo, hi = b
    return count >= lo and (hi is None or count <= hi)


def label(source: str | None, target: str | None) -> str:
    """Both ends for a line on a diagram or a table, source first: '1 : 0..*'; empty when neither is set."""
    s, t = (source or "").strip(), (target or "").strip()
    return f"{s or '*'} : {t or '*'}" if s or t else ""


def check(data: dict, entity: dict, constraints: list[dict]) -> list[str]:
    """The ways one entity breaks the multiplicities of its type's allowed relationships (data from eax.quality.load:
    rels, entities, types). Each constraint: type (relationship code), source_type_id, target_type_id, source_end,
    target_end, and the names for the message."""
    out = []
    rels = data["rels"].get(entity["id"], [])
    tid = entity["entity_type_id"]
    for c in constraints:
        for end, me, direction, other_type in (("target_end", c["source_type_id"], "out", c["target_type_id"]),
                                               ("source_end", c["target_type_id"], "in", c["source_type_id"])):
            if me != tid or not c.get(end):
                continue
            n = sum(1 for r in rels if r["dir"] == direction and r["type"].lower() == c["type"].lower()
                    and (data["entities"].get(r["other"]) or {}).get("entity_type_id") == other_type)
            if not fits(c[end], n):
                other = c["target_name"] if direction == "out" else c["source_name"]
                way = f"{c['type']} to" if direction == "out" else f"{c['type']} from"
                out.append(f"Has {n} {way} {other} ({c[end]} allowed)")
    return out
