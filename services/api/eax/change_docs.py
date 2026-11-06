"""Change documents (phase 8.1, WF-018): a page listing every change accepted into a model, with old and new values,
linked from a notification to everyone on the model. On screen only (D209).

Made for: a pushed metamodel package applied to a model (forced or accepted), a commit, a merge.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from .notify import _one, _rows

SKIP = {"id", "guid", "model_id", "entity_type_id", "created_at", "created_by", "modified_at", "modified_by", "version",
        "metamodel_version_created", "metamodel_version_changed", "search", "origin_guid", "row_version"}


def _plain(v):
    if v is None or v == "":
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)[:300]
    return str(v)[:300]


def _diff(before: dict | None, after: dict | None) -> list[dict]:
    b, a = before or {}, after or {}
    rows = []
    for k in sorted(set(b) | set(a)):
        if k in SKIP or k.startswith("_"):
            continue
        if b.get(k) != a.get(k):
            rows.append({"field": k.replace("_", " ").capitalize(), "old": _plain(b.get(k)), "new": _plain(a.get(k))})
    return rows


def save(conn, model_id: int, kind: str, title: str, summary: str, sections: list[dict], by: str) -> int:
    return conn.execute(text("""INSERT INTO core.change_documents (model_id, kind, title, summary, body, created_by)
                                VALUES (:m, :k, :t, :s, CAST(:b AS jsonb), :by) RETURNING id"""),
                        {"m": model_id, "k": kind, "t": title[:300], "s": summary[:2000],
                         "b": json.dumps({"sections": sections}, default=str), "by": by}).scalar_one()


def for_commit(conn, model_id: int, by: str, merged: bool = False) -> int | None:
    """The commit this transaction made (core.commits.tx), item by item with old and new values."""
    c = _one(conn, """SELECT id, number, message, committed_by, authors FROM core.commits
                       WHERE model_id = :m AND tx = txid_current() ORDER BY id DESC LIMIT 1""", m=model_id)
    if not c:
        return None
    items = _rows(conn, """SELECT i.op, i.label, i.author, i.target_kind, i.before, i.after, p.base, p.mine
                            FROM core.commit_items i LEFT JOIN core.pending_changes p ON p.id = i.change_id
                           WHERE i.commit_id = :c ORDER BY i.id""", c=c["id"])

    def js(v):
        return v if isinstance(v, (dict, list)) or v is None else json.loads(v or "null")
    rows = []
    for it in items:
        # what the change was made against and what it set (the uncommitted change), else the target before and after
        b, a = js(it["base"]), js(it["mine"])
        if not isinstance(a, dict) or not a:
            b, a = js(it["before"]), js(it["after"])
        elif isinstance(b, dict):
            b = {k: b.get(k) for k in a}
        whole = js(it["after"]) or js(it["before"]) or {}
        name = whole.get("name", "") if isinstance(whole, dict) else ""
        rows.append({"what": it["label"] or it["op"], "item": name, "by": it["author"], "fields": _diff(b, a)})
    word = "Merge" if merged else "Commit"
    title = f"{word} #{c['number']}" + (f": {c['message']}" if c["message"] else "")
    summary = f"{len(rows)} change{'s' if len(rows) != 1 else ''} by {', '.join(c['authors'] or [by])}, committed by {c['committed_by']}"
    return save(conn, model_id, "merge" if merged else "commit", title, summary,
                [{"title": "Content changes", "rows": rows}], by)


def for_push(conn, model_id: int, push: dict, target: dict, results: list[dict], impact: dict, by: str,
             parent_name: str, how: str) -> int:
    """A pushed metamodel package made in a model: each change with its note and what it made."""
    kinds = {"entity_type": "Entity type", "attribute": "Attribute", "pick_list": "Pick list", "lifecycle": "Lifecycle",
             "relationship_type": "Relationship type", "mapping": "Allowed relationship", "rule": "Rule"}
    rows = [{"what": r.get("note") or r.get("op"), "item": kinds.get(str(r.get("op", "")).split(".")[0], ""), "fields": [], "by": by}
            for r in results]
    for r, src in zip(rows, results, strict=True):
        made = (src.get("result") or {}) if isinstance(src.get("result"), dict) else {}
        if made.get("filled_with_default"):
            r["fields"].append({"field": "Filled with the default", "old": None,
                                "new": f"{made['filled_with_default']} existing entities"})
    sections = [{"title": f"Metamodel changes from {parent_name} (versions {', '.join(map(str, push['versions']))})",
                 "rows": rows}]
    if impact and impact.get("summary"):
        sections.append({"title": "Effect on the entities", "rows": [{"what": s, "item": "", "fields": []} for s in impact["summary"]]})
    title = f"Metamodel version {target.get('applied_version')} from {parent_name}"
    summary = f"{len(rows)} change{'s' if len(rows) != 1 else ''} {how} by {by}" + (f": {push['note']}" if push.get("note") else "")
    return save(conn, model_id, "metamodel", title, summary, sections, by)


def get(conn, guid, username: str, may_read_model) -> dict:
    ref = str(guid)
    where = "d.id = :g" if ref.isdigit() else "d.guid = CAST(:g AS uuid)"
    d = _one(conn, f"""SELECT d.*, m.guid AS model_guid, m.name AS model_name FROM core.change_documents d
                        JOIN core.models m ON m.id = d.model_id WHERE {where}""", g=int(ref) if ref.isdigit() else ref)
    if not d or not may_read_model(d["model_guid"]):
        raise LookupError("No such change document.")
    body = d["body"] if isinstance(d["body"], dict) else json.loads(d["body"] or "{}")
    return {"id": str(d["guid"]), "number": d["id"], "kind": d["kind"], "title": d["title"], "summary": d["summary"],
            "sections": body.get("sections", []), "created_by": d["created_by"], "created_at": d["created_at"],
            "model": {"id": str(d["model_guid"]), "name": d["model_name"]}}


def for_model(conn, model_id: int, limit: int = 100) -> list[dict]:
    return _rows(conn, """SELECT guid AS id, id AS number, kind, title, summary, created_by, created_at FROM core.change_documents
                           WHERE model_id = :m ORDER BY id DESC LIMIT :l""", m=model_id, l=limit)
