"""Business Model Canvases in a project (owner, 9 Nov 2026, D344): first-class, free-standing from the models.

    a canvas        the nine blocks (customer segments, value propositions, channels, customer relationships, revenue
                    streams, key resources, key activities, key partners, cost structure), each with its items. A
                    project has any number: kind current state, target state, working copy or scenario; draft or agreed
    lineage         an item keeps its lineage in every copy of the canvas, so two canvases compare item by item
    working copy    a copy where changes are marked by hand: an added item is green, a changed one amber with its old
                    text, a removed one crossed out in red (kept until the copy is cleaned up). "Make a clean canvas"
                    makes a new one (a target, say) without the removed items and without the marks
    compare         two canvases: added (green), changed (amber, old text crossed out), removed (crossed out in red);
                    "make a working copy of the changes" starts a working copy from the first with the second's changes
                    marked, to be adjusted and cleaned up into a new target
    export          PDF, PowerPoint and draw.io, of a canvas (with its marks) or of a comparison
    documents       what was used to build a canvas: uploaded with it (kept in 00_Project/Business model canvases) or a
                    document of the project, linked
    another project a canvas is copied into another project (contributors of both); its documents stay behind

Anyone on the project reads them; contributors change them; a change to an agreed canvas makes it a draft again.
Every change is kept (canvas_events). Rules are here, never in the database (D248).
"""

from __future__ import annotations

import io
import re
import textwrap
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy import text

from . import blank_files as bf
from . import project_work as pw
from . import projects as pj
from .metamodel_edit import EditError

_rows, _one = pj._rows, pj._one

# (key, label, the question it answers: our own words)
BLOCKS = [
    ("key_partners", "Key partners", "Who do we rely on: suppliers, partners, alliances?"),
    ("key_activities", "Key activities", "What must we do well to deliver the value?"),
    ("key_resources", "Key resources", "What must we have: people, systems, data, brands, money?"),
    ("value_propositions", "Value propositions", "What value do we give each customer segment?"),
    ("customer_relationships", "Customer relationships", "What relationship does each segment expect?"),
    ("channels", "Channels", "How do we reach, sell to and serve them?"),
    ("customer_segments", "Customer segments", "Whom do we create value for?"),
    ("cost_structure", "Cost structure", "What are the main costs?"),
    ("revenue_streams", "Revenue streams", "What do customers pay for, and how?"),
]
BLOCK_KEYS = [b[0] for b in BLOCKS]
LABEL = {k: label for k, label, _q in BLOCKS}
KINDS = {"current": "Current state", "target": "Target state", "working": "Working copy", "scenario": "Scenario"}
STATUSES = {"draft": "Draft", "agreed": "Agreed"}


def _clean(s: Any, n: int = 2000) -> str:
    return " ".join(str(s or "").split())[:n] if n <= 300 else str(s or "").strip()[:n]


# ---------------------------------------------------------------- reading
def _project(conn, project: Any, user, what: str) -> dict:
    p = pj.project_row(conn, project)
    pw.need(conn, p, user, what)
    return p


def _canvas(conn, p: dict, cid: str) -> dict:
    c = _one(conn, "SELECT * FROM proj.canvases WHERE project_id = :p AND guid::text = :g", p=p["id"], g=str(cid))
    if not c:
        raise EditError("No such canvas in this project.", 404)
    return c


def listing(conn, project: Any, user) -> dict:
    p = _project(conn, project, user, "read")
    rows = _rows(conn, """SELECT c.guid::text AS id, c.name, c.kind, c.status, c.description, c.source_note, s.guid::text AS source,
                                 s.name AS source_name, c.created_by, c.created_at, c.changed_by, c.changed_at,
                                 (SELECT count(*) FROM proj.canvas_items i WHERE i.canvas_id = c.id) AS items,
                                 (SELECT count(*) FROM proj.canvas_items i WHERE i.canvas_id = c.id AND i.mark <> '') AS marks
                            FROM proj.canvases c LEFT JOIN proj.canvases s ON s.id = c.source_id
                           WHERE c.project_id = :p ORDER BY c.created_at, c.id""", p=p["id"])
    return {"canvases": rows, "blocks": [{"key": k, "label": label, "question": q} for k, label, q in BLOCKS], "kinds": KINDS,
            "statuses": STATUSES}


def _items(conn, cid: int) -> list[dict]:
    return _rows(conn, """SELECT guid::text AS id, block, sort_order, text, note, lineage::text AS lineage, mark, was_text,
                                 changed_by, changed_at FROM proj.canvas_items WHERE canvas_id = :c ORDER BY block, sort_order, id""", c=cid)


def get(conn, project: Any, user, cid: str) -> dict:
    p = _project(conn, project, user, "read")
    c = _canvas(conn, p, cid)
    src = _one(conn, "SELECT guid::text AS id, name FROM proj.canvases WHERE id = :i", i=c["source_id"]) if c["source_id"] else None
    items = _items(conn, c["id"])
    return {"id": str(c["guid"]), "name": c["name"], "kind": c["kind"], "status": c["status"], "description": c["description"],
            "source": src, "source_note": c["source_note"], "created_by": c["created_by"], "created_at": c["created_at"],
            "changed_by": c["changed_by"], "changed_at": c["changed_at"],
            "blocks": {k: [i for i in items if i["block"] == k] for k in BLOCK_KEYS},
            "documents": _rows(conn, """SELECT d.guid::text AS id, d.file_name, d.title, d.folder, d.versions, cd.note, cd.added_by, cd.added_at
                                          FROM proj.canvas_documents cd JOIN proj.documents d ON d.id = cd.document_id
                                         WHERE cd.canvas_id = :c ORDER BY cd.added_at""", c=c["id"]),
            "history": _rows(conn, "SELECT action, username, at, note FROM proj.canvas_events WHERE canvas_id = :c ORDER BY at, id", c=c["id"])}


# ---------------------------------------------------------------- canvases
def _event(conn, cid: int, user, action: str, note: str = "") -> None:
    conn.execute(text("INSERT INTO proj.canvas_events (canvas_id, action, username, note) VALUES (:c, :a, :u, :n)"),
                 {"c": cid, "a": action, "u": user.username, "n": _clean(note, 1000)})


def _touch(conn, c: dict, user, action: str, note: str = "") -> str:
    """A change: kept, and an agreed canvas is a draft again."""
    again = c["status"] == "agreed"
    conn.execute(text("UPDATE proj.canvases SET changed_by = :u, changed_at = now(), status = 'draft' WHERE id = :i"),
                 {"u": user.username, "i": c["id"]})
    _event(conn, c["id"], user, action, note + (" (it was agreed: a draft again)" if again else ""))
    return " It was agreed: it is a draft again." if again else ""


def _new(conn, p: dict, user, name: str, kind: str, description: str = "", source: dict | None = None, note: str = "") -> dict:
    name = _clean(name, 200)
    if not name:
        raise EditError("Name the canvas.")
    if kind not in KINDS:
        raise EditError(f"A canvas is one of: {', '.join(KINDS.values())}.")
    if _one(conn, "SELECT 1 AS x FROM proj.canvases WHERE project_id = :p AND lower(name) = lower(:n)", p=p["id"], n=name):
        raise EditError(f"The project has a canvas called {name} already.", 409)
    c = _one(conn, """INSERT INTO proj.canvases (project_id, name, kind, description, source_id, source_note, created_by)
                      VALUES (:p, :n, :k, :d, :s, :sn, :u) RETURNING *""",
             p=p["id"], n=name, k=kind, d=_clean(description), s=source["id"] if source else None, sn=note, u=user.username)
    _event(conn, c["id"], user, "made", note)
    return c


def create(conn, project: Any, user, data: dict) -> dict:
    p = _project(conn, project, user, "contribute")
    c = _new(conn, p, user, data.get("name"), data.get("kind") or "current", data.get("description") or "")
    return {"id": str(c["guid"]), "message": f"Canvas {c['name']} made."}


def change(conn, project: Any, user, cid: str, data: dict) -> dict:
    """Name, kind, status (draft | agreed) or description."""
    p = _project(conn, project, user, "contribute")
    c = _canvas(conn, p, cid)
    name = _clean(data.get("name", c["name"]), 200)
    kind = data.get("kind", c["kind"])
    status = data.get("status", c["status"])
    if not name:
        raise EditError("Name the canvas.")
    if kind not in KINDS or status not in STATUSES:
        raise EditError("Unknown kind or status.")
    if name.lower() != c["name"].lower() and _one(conn, "SELECT 1 AS x FROM proj.canvases WHERE project_id = :p AND lower(name) = lower(:n)",
                                                  p=p["id"], n=name):
        raise EditError(f"The project has a canvas called {name} already.", 409)
    marks = _one(conn, "SELECT count(*) AS n FROM proj.canvas_items WHERE canvas_id = :c AND mark <> ''", c=c["id"])["n"]
    if c["kind"] == "working" and kind != "working" and marks:
        raise EditError("A working copy with marks is not a clean canvas: make a clean canvas from it instead.", 409)
    conn.execute(text("""UPDATE proj.canvases SET name = :n, kind = :k, status = :s, description = :d, changed_by = :u, changed_at = now()
                          WHERE id = :i"""), {"n": name, "k": kind, "s": status, "d": _clean(data.get("description", c["description"])),
                                              "u": user.username, "i": c["id"]})
    what = [w for w, on in (("renamed", name != c["name"]), (f"now {KINDS[kind].lower()}", kind != c["kind"]),
                            ("agreed" if status == "agreed" else "a draft again", status != c["status"])) if on]
    _event(conn, c["id"], user, "changed", ", ".join(what))
    return {"id": cid, "message": f"{name}: {', '.join(what) or 'saved'}."}


def delete(conn, project: Any, user, cid: str) -> dict:
    p = _project(conn, project, user, "contribute")
    c = _canvas(conn, p, cid)
    conn.execute(text("DELETE FROM proj.canvases WHERE id = :i"), {"i": c["id"]})
    return {"id": cid, "message": f"Canvas {c['name']} removed."}


# ---------------------------------------------------------------- items
def _item(conn, p: dict, iid: str) -> tuple[dict, dict]:
    it = _one(conn, """SELECT i.* FROM proj.canvas_items i JOIN proj.canvases c ON c.id = i.canvas_id
                        WHERE c.project_id = :p AND i.guid::text = :g""", p=p["id"], g=str(iid))
    if not it:
        raise EditError("No such item on a canvas of this project.", 404)
    return it, _one(conn, "SELECT * FROM proj.canvases WHERE id = :i", i=it["canvas_id"])


def add_item(conn, project: Any, user, cid: str, data: dict) -> dict:
    p = _project(conn, project, user, "contribute")
    c = _canvas(conn, p, cid)
    block, t = data.get("block"), _clean(data.get("text"), 300)
    if block not in BLOCK_KEYS:
        raise EditError("Choose the block.")
    if not t:
        raise EditError("Write the item.")
    seq = _one(conn, "SELECT coalesce(max(sort_order), 0) + 1 AS n FROM proj.canvas_items WHERE canvas_id = :c AND block = :b",
               c=c["id"], b=block)["n"]
    row = _one(conn, """INSERT INTO proj.canvas_items (canvas_id, block, sort_order, text, note, mark, changed_by, changed_at)
                        VALUES (:c, :b, :s, :t, :n, :m, :u, now()) RETURNING guid::text AS id""",
               c=c["id"], b=block, s=seq, t=t, n=_clean(data.get("note"), 2000), m="added" if c["kind"] == "working" else "", u=user.username)
    more = _touch(conn, c, user, "item added", f"{LABEL[block]}: {t}")
    return {"id": row["id"], "message": f"Added to {LABEL[block]}." + more}


def change_item(conn, project: Any, user, iid: str, data: dict) -> dict:
    """Its text, note or block. In a working copy a changed item is marked, its first text kept to show crossed out;
    changed back to that text, the mark goes."""
    p = _project(conn, project, user, "contribute")
    it, c = _item(conn, p, iid)
    t = _clean(data.get("text", it["text"]), 300)
    if not t:
        raise EditError("Write the item (or remove it).")
    block = data.get("block", it["block"])
    if block not in BLOCK_KEYS:
        raise EditError("Unknown block.")
    mark, was = it["mark"], it["was_text"]
    if c["kind"] == "working" and t != it["text"] and mark != "added":
        if mark == "changed" and t == was:
            mark, was = "", ""
        elif mark != "changed":
            mark, was = "changed", it["text"]
    seq = it["sort_order"] if block == it["block"] else _one(
        conn, "SELECT coalesce(max(sort_order), 0) + 1 AS n FROM proj.canvas_items WHERE canvas_id = :c AND block = :b", c=c["id"], b=block)["n"]
    conn.execute(text("""UPDATE proj.canvas_items SET text = :t, note = :n, block = :b, sort_order = :s, mark = :m, was_text = :w,
                                changed_by = :u, changed_at = now() WHERE id = :i"""),
                 {"t": t, "n": _clean(data.get("note", it["note"]), 2000), "b": block, "s": seq, "m": mark, "w": was,
                  "u": user.username, "i": it["id"]})
    more = _touch(conn, c, user, "item changed", f"{LABEL[block]}: {it['text']}" + (f" → {t}" if t != it["text"] else ""))
    return {"id": iid, "message": "Saved." + more}


def remove_item(conn, project: Any, user, iid: str) -> dict:
    """In a working copy the item is crossed out (kept until the copy is cleaned up; an item added in it goes at once);
    anywhere else it goes."""
    p = _project(conn, project, user, "contribute")
    it, c = _item(conn, p, iid)
    if c["kind"] == "working" and it["mark"] != "added":
        conn.execute(text("UPDATE proj.canvas_items SET mark = 'removed', changed_by = :u, changed_at = now() WHERE id = :i"),
                     {"u": user.username, "i": it["id"]})
        msg = "Crossed out: it goes when a clean canvas is made from this working copy."
    else:
        conn.execute(text("DELETE FROM proj.canvas_items WHERE id = :i"), {"i": it["id"]})
        msg = "Removed."
    return {"id": iid, "message": msg + _touch(conn, c, user, "item removed", f"{LABEL[it['block']]}: {it['text']}")}


def restore_item(conn, project: Any, user, iid: str) -> dict:
    """Undo a working copy's mark: a crossed-out item comes back, a changed one gets its first text again."""
    p = _project(conn, project, user, "contribute")
    it, c = _item(conn, p, iid)
    if it["mark"] == "removed":
        conn.execute(text("UPDATE proj.canvas_items SET mark = '' WHERE id = :i"), {"i": it["id"]})
    elif it["mark"] == "changed":
        conn.execute(text("UPDATE proj.canvas_items SET mark = '', text = was_text, was_text = '' WHERE id = :i"), {"i": it["id"]})
    else:
        return {"id": iid, "message": "Nothing to undo."}
    return {"id": iid, "message": "Back as it was." + _touch(conn, c, user, "mark undone", f"{LABEL[it['block']]}: {it['text']}")}


def reorder(conn, project: Any, user, cid: str, block: str, ids: list[str]) -> dict:
    p = _project(conn, project, user, "contribute")
    c = _canvas(conn, p, cid)
    for n, g in enumerate(ids or [], start=1):
        conn.execute(text("UPDATE proj.canvas_items SET sort_order = :s WHERE canvas_id = :c AND block = :b AND guid::text = :g"),
                     {"s": n, "c": c["id"], "b": block, "g": str(g)})
    return {"id": cid, "message": "Order saved."}


# ---------------------------------------------------------------- copies and clean-up
def _copy_items(conn, src: dict, dst: dict, keep_marks: bool) -> int:
    n = 0
    for it in _rows(conn, "SELECT * FROM proj.canvas_items WHERE canvas_id = :c ORDER BY block, sort_order, id", c=src["id"]):
        if not keep_marks and it["mark"] == "removed":
            continue
        conn.execute(text("""INSERT INTO proj.canvas_items (canvas_id, block, sort_order, text, note, lineage, mark, was_text)
                             VALUES (:c, :b, :s, :t, :n, :l, :m, :w)"""),
                     {"c": dst["id"], "b": it["block"], "s": it["sort_order"], "t": it["text"], "n": it["note"], "l": it["lineage"],
                      "m": it["mark"] if keep_marks else "", "w": it["was_text"] if keep_marks else ""})
        n += 1
    return n


def copy(conn, project: Any, user, cid: str, data: dict) -> dict:
    """A copy of a canvas: a working copy by default (to change by hand), or any other kind. A working copy copied as a
    working copy keeps its marks; otherwise the copy is clean (crossed-out items left out, no marks)."""
    p = _project(conn, project, user, "contribute")
    src = _canvas(conn, p, cid)
    kind = data.get("kind") or "working"
    name = data.get("name") or f"{src['name']} ({KINDS[kind].lower()})"
    keep = kind == "working" and src["kind"] == "working"
    c = _new(conn, p, user, name, kind, data.get("description") or "", src, f"a {KINDS[kind].lower()} of {src['name']}")
    n = _copy_items(conn, src, c, keep)
    return {"id": str(c["guid"]), "message": f"{c['name']} made from {src['name']} ({n} items)."}


def clean_up(conn, project: Any, user, cid: str, data: dict) -> dict:
    """A new canvas from a working copy, cleaned up: the crossed-out items left out and the marks gone (a target state
    by default). The working copy stays as it is."""
    p = _project(conn, project, user, "contribute")
    src = _canvas(conn, p, cid)
    kind = data.get("kind") or "target"
    c = _new(conn, p, user, data.get("name") or f"{src['name']} (clean)", kind, data.get("description") or "", src,
             f"cleaned up from {src['name']}")
    n = _copy_items(conn, src, c, False)
    gone = _one(conn, "SELECT count(*) AS n FROM proj.canvas_items WHERE canvas_id = :c AND mark = 'removed'", c=src["id"])["n"]
    return {"id": str(c["guid"]), "message": f"{c['name']} made: {n} items, {gone} crossed-out item{'s' if gone != 1 else ''} left out."}


def copy_to(conn, project: Any, user, cid: str, target: str, data: dict) -> dict:
    """A copy of the canvas in another project (read in this one, contribute in the other): clean, with the same
    lineage, so it still compares with this one if copied back. Its documents stay in this project."""
    p = _project(conn, project, user, "read")
    src = _canvas(conn, p, cid)
    t = pj.project_row(conn, target)
    pw.need(conn, t, user, "contribute")
    if t["id"] == p["id"]:
        return copy(conn, project, user, cid, data)
    kind = data.get("kind") or ("current" if src["kind"] == "working" else src["kind"])
    name = data.get("name") or src["name"]
    if _one(conn, "SELECT 1 AS x FROM proj.canvases WHERE project_id = :p AND lower(name) = lower(:n)", p=t["id"], n=name):
        name = f"{name} (from {p['name']})"
    c = _new(conn, t, user, name, kind, data.get("description") or src["description"], None, f"copied from {src['name']} in {p['name']}")
    n = _copy_items(conn, src, c, False)
    _event(conn, src["id"], user, "copied", f"to {t['name']}")
    return {"id": str(c["guid"]), "project": str(t["guid"]), "message": f"{c['name']} is in {t['name']} ({n} items)."}


# ---------------------------------------------------------------- the documents behind a canvas
CANVAS_FILES = "00_Project/Business model canvases"


def add_document(conn, project: Any, user, cid: str, data: dict, file_name: str = "", content: bytes = b"") -> dict:
    """Upload a document used to build the canvas, or link one of the project's documents ({document: id})."""
    p = _project(conn, project, user, "contribute")
    c = _canvas(conn, p, cid)
    if content:
        doc = pw._store(conn, p, user, CANVAS_FILES, file_name or "document", content, origin="canvas", kind="Artifact")
        g = doc["id"]
    else:
        g = data.get("document") or ""
    d = _one(conn, "SELECT id, file_name, title FROM proj.documents WHERE project_id = :p AND guid::text = :g", p=p["id"], g=str(g))
    if not d:
        raise EditError("Choose a file to upload, or a document of this project.")
    conn.execute(text("""INSERT INTO proj.canvas_documents (canvas_id, document_id, note, added_by) VALUES (:c, :d, :n, :u)
                         ON CONFLICT (canvas_id, document_id) DO UPDATE SET note = EXCLUDED.note"""),
                 {"c": c["id"], "d": d["id"], "n": _clean(data.get("note"), 1000), "u": user.username})
    _event(conn, c["id"], user, "document added", d["title"] or d["file_name"])
    return {"id": cid, "message": f"{d['title'] or d['file_name']} is with {c['name']}."}


def remove_document(conn, project: Any, user, cid: str, doc: str) -> dict:
    """The link goes; the document stays in the project's repository."""
    p = _project(conn, project, user, "contribute")
    c = _canvas(conn, p, cid)
    d = _one(conn, "SELECT id, file_name, title FROM proj.documents WHERE project_id = :p AND guid::text = :g", p=p["id"], g=str(doc))
    if d:
        conn.execute(text("DELETE FROM proj.canvas_documents WHERE canvas_id = :c AND document_id = :d"), {"c": c["id"], "d": d["id"]})
        _event(conn, c["id"], user, "document taken off", d["title"] or d["file_name"])
    return {"id": cid, "message": "Taken off the canvas (it stays in the project's documents)."}


# ---------------------------------------------------------------- compare
def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", (s or "").lower()).strip()


def _effective(conn, c: dict) -> list[dict]:
    """A canvas as it stands: a working copy's crossed-out items are not on it."""
    return [i for i in _items(conn, c["id"]) if i["mark"] != "removed"]


def diff(a_items: list[dict], b_items: list[dict]) -> dict[str, list[dict]]:
    """Each block of B against A: same, added, changed (new text, the old one kept), removed. Items are matched by their
    lineage, then by the same text in the same block. An item moved to another block shows as removed from the old
    block and added to the new one."""
    by_lin = {i["lineage"]: i for i in a_items}
    used: set[str] = set()
    pairs: list[tuple[dict | None, dict | None]] = []
    rest_b = []
    for b in b_items:
        a = by_lin.get(b["lineage"])
        if a and a["block"] == b["block"] and a["id"] not in used:
            used.add(a["id"])
            pairs.append((a, b))
        else:
            rest_b.append(b)
    for b in rest_b:
        a = next((x for x in a_items if x["id"] not in used and x["block"] == b["block"] and _norm(x["text"]) == _norm(b["text"])), None)
        if a:
            used.add(a["id"])
        pairs.append((a, b))
    pairs += [(a, None) for a in a_items if a["id"] not in used]
    out: dict[str, list[dict]] = {k: [] for k in BLOCK_KEYS}
    for a, b in pairs:
        x = b or a
        if a and b:
            same = a["text"] == b["text"] and (a.get("note") or "") == (b.get("note") or "")
            state, was = ("same", "") if same else ("changed", a["text"] if a["text"] != b["text"] else "")
        else:
            state, was = ("added" if b else "removed"), ""
        out[x["block"]].append({"state": state, "text": x["text"], "note": x.get("note") or "", "was_text": was,
                                "lineage": x["lineage"], "a": a and a["id"], "b": b and b["id"], "order": (b or a)["sort_order"]})
    for k in out:
        out[k].sort(key=lambda r: ({"same": 0, "changed": 0, "added": 1, "removed": 2}[r["state"]], r["order"]))
    return out


def compare(conn, project: Any, user, a: str, b: str) -> dict:
    p = _project(conn, project, user, "read")
    ca, cb = _canvas(conn, p, a), _canvas(conn, p, b)
    d = diff(_effective(conn, ca), _effective(conn, cb))
    counts = {s: sum(1 for k in d for r in d[k] if r["state"] == s) for s in ("same", "added", "changed", "removed")}
    return {"a": {"id": a, "name": ca["name"], "kind": ca["kind"]}, "b": {"id": b, "name": cb["name"], "kind": cb["kind"]},
            "blocks": d, "counts": counts}


def from_compare(conn, project: Any, user, a: str, b: str, data: dict) -> dict:
    """A working copy of the changes from A to B: A's items, with B's changes marked (added, changed with A's text kept,
    removed crossed out), to adjust by hand and clean up into a new canvas."""
    p = _project(conn, project, user, "contribute")
    ca, cb = _canvas(conn, p, a), _canvas(conn, p, b)
    c = _new(conn, p, user, data.get("name") or f"{ca['name']} to {cb['name']} (working copy)", "working", data.get("description") or "",
             ca, f"the changes from {ca['name']} to {cb['name']}")
    d = diff(_effective(conn, ca), _effective(conn, cb))
    n = 0
    for block, rows in d.items():
        for seq, r in enumerate(rows, start=1):
            mark = {"same": "", "added": "added", "changed": "changed", "removed": "removed"}[r["state"]]
            conn.execute(text("""INSERT INTO proj.canvas_items (canvas_id, block, sort_order, text, note, lineage, mark, was_text)
                                 VALUES (:c, :b, :s, :t, :n, CAST(:l AS uuid), :m, :w)"""),
                         {"c": c["id"], "b": block, "s": seq, "t": r["text"], "n": r["note"], "l": r["lineage"], "m": mark,
                          "w": r["was_text"] if mark == "changed" else ""})
            n += 1
    return {"id": str(c["guid"]), "message": f"{c['name']} made: {n} items with the changes marked."}


# ---------------------------------------------------------------- export: PDF, PowerPoint, draw.io
# the classic layout on a 1600 x 1000 board: five columns on top (partners; activities over resources; value
# propositions; relationships over channels; segments), costs and revenue below
TOP_H, W = 650, 1600
COLS = [("key_partners",), ("key_activities", "key_resources"), ("value_propositions",),
        ("customer_relationships", "channels"), ("customer_segments",)]
STYLE = {"same": ("FFFFFF", "8A96A3", "1F2328"), "": ("FFF7D6", "C9B458", "1F2328"),
         "added": ("DAFBE1", "1A7F37", "1A7F37"), "changed": ("FFF8C5", "BF8700", "7D4E00"), "removed": ("FFEBE9", "CF222E", "CF222E")}


def _boxes() -> dict[str, tuple[int, int, int, int]]:
    out, cw = {}, W // 5
    for n, col in enumerate(COLS):
        h = TOP_H // len(col)
        for m, k in enumerate(col):
            out[k] = (n * cw, m * h, cw, h)
    out["cost_structure"] = (0, TOP_H, W // 2, 1000 - TOP_H)
    out["revenue_streams"] = (W // 2, TOP_H, W // 2, 1000 - TOP_H)
    return out


def view(conn, project: Any, user, cid: str, other: str = "") -> dict:
    """What an export draws: a canvas with its marks, or the comparison of two."""
    if other:
        cmp = compare(conn, project, user, cid, other)
        return {"title": f"{cmp['a']['name']} → {cmp['b']['name']}", "subtitle": "Comparison: green added, amber changed, red crossed out removed",
                "blocks": {k: [{"state": r["state"], "text": r["text"], "note": r["note"], "was_text": r["was_text"]} for r in rows]
                           for k, rows in cmp["blocks"].items()}}
    c = get(conn, project, user, cid)
    sub = f"{KINDS[c['kind']]} · {STATUSES[c['status']]}" + (" · marks: green added, amber changed, red crossed out removed"
                                                              if c["kind"] == "working" else "")
    return {"title": c["name"], "subtitle": sub,
            "blocks": {k: [{"state": i["mark"] or "same", "text": i["text"], "note": i["note"], "was_text": i["was_text"]} for i in rows]
                       for k, rows in c["blocks"].items()}}


def export(conn, project: Any, user, cid: str, fmt: str, other: str = "") -> tuple[bytes, str, str]:
    v = view(conn, project, user, cid, other)
    name = bf.file_name(v["title"].replace("→", "to"), {"pdf": "pdf", "pptx": "pptx", "drawio": "drawio"}.get(fmt, "x"))
    if fmt == "pdf":
        return _pdf(v), name, "application/pdf"
    if fmt == "pptx":
        return _pptx(v), name, "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if fmt == "drawio":
        return _drawio(v).encode(), name, "application/xml"
    raise EditError("Export as pdf, pptx or drawio.")


def _lines(s: str, width: int) -> list[str]:
    return textwrap.wrap(s, width) or [""]


def _drawio(v: dict) -> str:
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    title = f'<b style="font-size:18px">{escape(v["title"])}</b><br><span style="color:#5b6775">{escape(v["subtitle"])}</span>'
    cells.append(f'<mxCell id="title" value="{escape(title, {chr(34): "&quot;"})}" style="text;html=1;align=left;verticalAlign=top;" '
                 f'vertex="1" parent="1"><mxGeometry x="0" y="-60" width="1600" height="50" as="geometry"/></mxCell>')
    boxes = _boxes()
    for k, (x, y, w, h) in boxes.items():
        rows = v["blocks"].get(k, [])
        need = 34 + sum(14 * (len(_lines(r["text"], 34)) + (len(_lines(r["was_text"], 34)) if r["was_text"] else 0)) + 16 for r in rows)
        h2 = max(h, need)
        cells.append(f'<mxCell id="b_{k}" value="&lt;b&gt;{escape(LABEL[k])}&lt;/b&gt;" style="rounded=0;whiteSpace=wrap;html=1;'
                     f'verticalAlign=top;align=left;spacingLeft=8;fillColor=#F6F8FA;strokeColor=#57606A;container=1;collapsible=0;" '
                     f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h2}" as="geometry"/></mxCell>')
        top = 30
        for n, r in enumerate(rows):
            fill, stroke, font = STYLE[r["state"]]
            lab = escape(r["text"])
            if r["was_text"]:
                lab = f"<s>{escape(r['was_text'])}</s><br>{lab}"
            if r["note"]:
                lab += f'<br><font color="#5B6775" style="font-size:10px">{escape(r["note"][:200])}</font>'
            ih = 14 * (len(_lines(r["text"], 34)) + (len(_lines(r["was_text"], 34)) if r["was_text"] else 0) + (1 if r["note"] else 0)) + 10
            fs = 8 if r["state"] == "removed" else 0
            cells.append(f'<mxCell id="i_{k}_{n}" value="{escape(lab, {chr(34): "&quot;"})}" style="rounded=1;arcSize=8;whiteSpace=wrap;html=1;'
                         f'align=left;spacingLeft=6;fontSize=12;fillColor=#{fill};strokeColor=#{stroke};fontColor=#{font};fontStyle={fs};" '
                         f'vertex="1" parent="b_{k}"><mxGeometry x="8" y="{top}" width="{w - 16}" height="{ih}" as="geometry"/></mxCell>')
            top += ih + 6
    return ('<mxfile host="EA Explorer"><diagram id="bmc" name="' + escape(v["title"], {'"': "&quot;"}) +
            '"><mxGraphModel grid="1" gridSize="10" page="0"><root>' + "".join(cells) + "</root></mxGraphModel></diagram></mxfile>")


def _rgb(h: str):
    from reportlab.lib.colors import HexColor
    return HexColor("#" + h)


def _pdf(v: dict) -> bytes:
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas as rl
    buf = io.BytesIO()
    pw_, ph = landscape(A3)
    c = rl.Canvas(buf, pagesize=(pw_, ph))
    c.setTitle(v["title"])
    m = 36
    sx = (pw_ - 2 * m) / W
    sy = (ph - 2 * m - 50) / 1000
    c.setFont("Helvetica-Bold", 18)
    c.drawString(m, ph - m - 14, v["title"][:110])
    c.setFont("Helvetica", 10)
    c.setFillColor(_rgb("5B6775"))
    c.drawString(m, ph - m - 30, v["subtitle"][:200])
    top0 = ph - m - 50
    for k, (x, y, w, h) in _boxes().items():
        bx, by, bw, bh = m + x * sx, top0 - (y + h) * sy, w * sx, h * sy
        c.setStrokeColor(_rgb("57606A"))
        c.setFillColor(_rgb("F6F8FA"))
        c.rect(bx, by, bw, bh, stroke=1, fill=1)
        c.setFillColor(_rgb("1F2328"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(bx + 6, by + bh - 15, LABEL[k])
        rows = v["blocks"].get(k, [])
        size = 9 if sum(len(r["text"]) for r in rows) < 600 else 7.5
        cy = by + bh - 24
        for r in rows:
            fill, stroke, font = STYLE[r["state"]]
            lines = (simpleSplit(r["was_text"], "Helvetica", size, bw - 20) if r["was_text"] else []) + simpleSplit(r["text"], "Helvetica", size, bw - 20)
            ih = len(lines) * (size + 2) + 6
            if cy - ih < by + 4:
                c.setFillColor(_rgb("5B6775"))
                c.setFont("Helvetica-Oblique", size)
                c.drawString(bx + 6, by + 5, "… more on the canvas")
                break
            c.setFillColor(_rgb(fill))
            c.setStrokeColor(_rgb(stroke))
            c.roundRect(bx + 5, cy - ih, bw - 10, ih, 3, stroke=1, fill=1)
            ly = cy - size - 2
            n_old = len(simpleSplit(r["was_text"], "Helvetica", size, bw - 20)) if r["was_text"] else 0
            for n, ln in enumerate(lines):
                old = n < n_old
                c.setFillColor(_rgb("CF222E" if old else font))
                c.setFont("Helvetica", size)
                c.drawString(bx + 10, ly, ln)
                if old or r["state"] == "removed":
                    wd = c.stringWidth(ln, "Helvetica", size)
                    c.setStrokeColor(_rgb("CF222E"))
                    c.line(bx + 10, ly + size * 0.3, bx + 10 + wd, ly + size * 0.3)
                ly -= size + 2
            cy -= ih + 4
    c.showPage()
    c.save()
    return buf.getvalue()


def _pptx(v: dict) -> bytes:
    """One slide, a shape per block, each item a paragraph: added green, changed amber with the old text struck through,
    removed red and struck through. The text shrinks to fit in PowerPoint."""
    emu_x, emu_y, ox, oy = 11277600 / W, 5486400 / 1000, 457200, 1066800
    shapes, sid = [], 3

    def run(t, colour="1F2328", strike=False, bold=False, sz=1100):
        b = ' b="1"' if bold else ""
        st = ' strike="sngStrike"' if strike else ""
        return (f'<a:r><a:rPr lang="en-GB" sz="{sz}"{b}{st}><a:solidFill><a:srgbClr val="{colour}"/></a:solidFill></a:rPr>'
                f'<a:t>{escape(t)}</a:t></a:r>')
    for k, (x, y, w, h) in _boxes().items():
        rows = v["blocks"].get(k, [])
        paras = [f"<a:p>{run(LABEL[k], bold=True, sz=1200)}</a:p>"]
        for r in rows:
            colour = STYLE[r["state"]][2] if r["state"] != "same" else "1F2328"
            body = (run(r["was_text"], "CF222E", strike=True) + run("  ") if r["was_text"] else "") + \
                run(r["text"], colour, strike=r["state"] == "removed")
            paras.append(f'<a:p><a:pPr marL="171450" indent="-171450"><a:buChar char="•"/></a:pPr>{body}</a:p>')
        shapes.append(f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{escape(LABEL[k])}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
                      f'<p:spPr><a:xfrm><a:off x="{ox + int(x * emu_x)}" y="{oy + int(y * emu_y)}"/><a:ext cx="{int(w * emu_x)}" cy="{int(h * emu_y)}"/></a:xfrm>'
                      '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="F6F8FA"/></a:solidFill>'
                      '<a:ln w="9525"><a:solidFill><a:srgbClr val="57606A"/></a:solidFill></a:ln></p:spPr>'
                      '<p:txBody><a:bodyPr wrap="square" lIns="72000" tIns="54000" rIns="72000" bIns="36000" anchor="t">'
                      f'<a:normAutofit fontScale="{max(40000, 100000 - 3500 * max(0, len(rows) - 4))}" lnSpcReduction="10000"/></a:bodyPr><a:lstStyle/>'
                      + "".join(paras) + "</p:txBody></p:sp>")
        sid += 1
    head = (f'<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm>'
            '<a:off x="457200" y="228600"/><a:ext cx="11277600" cy="762000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p>{run(v["title"], bold=True, sz=2400)}</a:p><a:p>{run(v["subtitle"], "5B6775", sz=1200)}</a:p>'
            '</p:txBody></p:sp>')
    return bf.pptx_slide(v["title"], head + "".join(shapes))
