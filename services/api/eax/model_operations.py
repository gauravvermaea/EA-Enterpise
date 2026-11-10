"""Model operations as plain functions (phases 26/27, D458, D484): the same operations the MCP tools run (eax.mcp_ops),
without the MCP wrapping, for scenario planning (27.1), the sample data and anything else that needs them. Each runs as
the person given, with the same checks as the screens (model_ops, merge_back, model_wizards)."""

from __future__ import annotations

from typing import Any

from . import repository as repo
from .metamodel_edit import EditError


def copy_or_child(conn, user, source: Any, name: str, linked: bool = True, copy: str = "content", description: str = "",
                  tag: str = "") -> dict:
    """A copy of a model: a child linked to it (linked, it can merge back and override it) or a separate copy; its
    content copied straight away. Needs the right to create models (the same check as the screens)."""
    from . import model_ops as mo
    from . import tags as tg
    src = repo.get_model(conn, source)
    spec = {"kind": "project", "name": name, "description": description, "industry": src.get("industry") or "",
            "source": str(src["id"]), "copy": copy}
    if linked:
        if src["kind"] != "project":
            raise EditError(f"{src['name']} is a {src['kind']} model: a linked copy (child) is made of a project model only. Make a separate copy.")
        spec["parent"] = str(src["id"])
    if tag:
        if linked:
            raise EditError("A copy made from a tag is a separate copy: use linked=false.")
        found = [t for t in tg.list_tags(conn, str(src["id"])).get("tags", []) if tag in (str(t.get("id")), t.get("name"))]
        if not found:
            raise EditError(f"{src['name']} has no tag '{tag}'.")
        spec["tag"] = str(found[0]["id"])
    out = mo.create_model(conn, user.username, spec)
    for c in [out.get("_copy")] if out.get("_copy") else []:
        mo.run_copy(conn, c["source"], c["target"], user.username)
    m = repo.get_model(conn, str(out["model"]["id"]))
    return {"model": str(m["id"]), "name": m["name"], "parent": src["name"] if linked else None, "entities": m.get("entity_count"),
            "link": f"/#/metamodel/{m['id']}"}


def tag_before(conn, user, model: Any, why: str) -> dict:
    """Tags a model as it is now before a change (the model wizards' tag first)."""
    from . import model_wizards as mw
    t = mw.tag_first(conn, model, user, why)
    return {"model": str(model), "tag": t.get("name"), "tag_id": str(t.get("id") or "")}


def compare_now(conn, left: Any, right: Any, left_tag: str = "", right_tag: str = "") -> dict:
    """Two models (or tags of them) compared: totals per type, the first 200 differences, metamodel differences."""
    from . import compare
    lft = compare.load_side(conn, {"kind": "tag", "id": left_tag} if left_tag else {"kind": "model", "id": left})
    rgt = compare.load_side(conn, {"kind": "tag", "id": right_tag} if right_tag else {"kind": "model", "id": right})
    res = compare.compare(lft, rgt)
    return {**{k: res[k] for k in ("left", "right", "totals", "relationship_totals", "summary")},
            "differences": [i for i in res["items"] if i["status"] != "kept"][:200], "metamodel": res["metamodel"][:100]}



def override(conn, user, model: Any, note: str = "", after: str = "none") -> dict:
    """The child overrides its parent: sent for merge, every change accepted (conflicts take the child's value), merged
    (the parent is tagged first by the merge); then, if asked, the child is frozen or refreshed. The person's own
    rights are checked by each step (merge_back)."""
    from . import merge_back as mb
    child = repo.get_model(conn, model)
    parent = mb._parent(conn, child)
    req = mb.send(conn, model, user, note or "Override through MCP: every change accepted (D458).")
    full = mb.get(conn, req["id"], user)
    mb.decide(conn, req["id"], user, {c["id"]: {"accept": True, "reason": ""} for c in full.get("changes") or []})
    merged = mb.merge(conn, req["id"], user)
    out = {"request": req["id"], "number": req.get("number"), "parent": parent["name"], "child": child["name"],
           "merged": {k: merged.get(k) for k in ("status", "report", "message", "commit") if k in merged},
           "link": f"/#/merge-requests/{req['id']}",
           "message": f"{child['name']} overrode {parent['name']}: every change merged (merge request {req.get('number')})."}
    if after != "none":
        fin = mb.finish(conn, req["id"], user, after)
        out["after"] = after
        out["message"] += " " + str(fin.get("message") or "")
    return out
