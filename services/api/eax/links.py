"""Link attributes (data type code ``url``, D418).

A Link value is one or more links, each an address and an optional note (a version, what it is), kept in value_text
as one line per link: ``address | note``. A plain single address (as stored before D418) is a valid value.

People enter anything (owner, 10 Nov 2026): nothing is refused for its content. The only limits are plain field
limits (2,000 characters an address, 200 a note, 20 links), applied by trimming. The one safety guard is for display
only: an address is shown as a clickable link only when it starts with http(s)://, ftp(s):// or is an EA Explorer
link (#/..., ea:... or the same host); anything else shows as plain text, so nothing harmful runs when clicked.
"""

from __future__ import annotations

import json
import re
from typing import Any

MAX_ADDRESS = 2000
MAX_NOTE = 200
MAX_LINKS = 20
SEPARATOR = " | "

_CLICKABLE = re.compile(r"^(https?|ftps?)://", re.IGNORECASE)


def _line(address: str, note: str) -> str:
    address = " ".join(str(address or "").split())[:MAX_ADDRESS]
    note = " ".join(str(note or "").split())[:MAX_NOTE]
    return f"{address}{SEPARATOR}{note}" if note else address


def parse(value: Any) -> list[dict]:
    """The links in a stored value (or anything given): [{address, note}], empty addresses left out."""
    if value is None:
        return []
    if isinstance(value, dict):
        value = [value]
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("[") or s.startswith("{"):
            try:
                return parse(json.loads(s))
            except ValueError:
                pass
        out = []
        for raw in s.splitlines():
            address, _, note = raw.partition("|")
            address, note = address.strip(), note.strip()
            if address:
                out.append({"address": address[:MAX_ADDRESS], "note": note[:MAX_NOTE]})
        return out[:MAX_LINKS]
    if isinstance(value, (list, tuple)):
        out = []
        for x in value:
            if isinstance(x, dict):
                address = str(x.get("address") or x.get("url") or x.get("href") or "").strip()
                note = str(x.get("note") or x.get("label") or "").strip()
            else:
                address, _, note = str(x or "").partition("|")
                address, note = address.strip(), note.strip()
            if address:
                out.append({"address": " ".join(address.split())[:MAX_ADDRESS], "note": " ".join(note.split())[:MAX_NOTE]})
        return out[:MAX_LINKS]
    return parse(str(value))


def store(value: Any) -> str | None:
    """The value as value_text keeps it (one line a link), or None when there is no link."""
    links = parse(value)
    return "\n".join(_line(x["address"], x["note"]) for x in links) or None


def clickable(address: str, host: str = "") -> bool:
    """Display only: whether the address is shown as a link (never a reason to refuse it)."""
    a = (address or "").strip()
    if _CLICKABLE.match(a):
        return True
    if a.startswith("#/") or re.match(r"^ea:(model|project|entity|view|canvas|reference|page):\S", a):
        return True
    return bool(host) and a.lower().startswith(f"//{host.lower()}/")


def text(value: Any) -> str:
    """For reports, history and anywhere plain text is wanted: "address (note)" joined by "; "."""
    return "; ".join(f"{x['address']} ({x['note']})" if x["note"] else x["address"] for x in parse(value))
