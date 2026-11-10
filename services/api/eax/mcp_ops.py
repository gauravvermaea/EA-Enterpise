"""Model operations through MCP (phases 26/27, D458, D484): whole operations from plain requests, such as "make a copy
of this model and remove all duplicates as you see fit", then "override its parent with it".

The owner reviews the changes himself, so a tool applies them without the screens' review steps, but every tool that
changes something follows the same rules (D458):

* it acts only with the person's own rights (the same functions and checks as the screens: merge requests 19/20,
  dedupe 21, the model wizards), and within the machine credential's MCP level (read-only gets reading tools only);
* it first returns a **preview** and a **confirm** token; it changes something only when called again with the same
  arguments and confirm=<token>, by the same person, within 30 minutes (core.mcp_previews);
* the model it changes is **tagged first**, so it can be restored;
* the change is the person's, in the change log, marked as done through MCP (audit source "mcp", action mcp.<tool>).

Credentials, roles and service accounts are never made through MCP.

For scenario planning (27.1) and other modules, the plain functions copy_or_child, tag_before and compare_now are the
same operations without the MCP wrapping.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from typing import Any

import anyio
from sqlalchemy import text

from . import audit, permissions
from . import repository as repo
from .db import get_engine
from .mcp_server import _clean, _run, cite, may_write, mcp, note_call
from .metamodel_edit import EditError
from .model_operations import (  # noqa: F401 - for 27.1 and others
    compare_now,
    copy_or_child,
    override,
    tag_before,
)
from .views_client import ViewsDown

PREVIEW_MINUTES = 30
ASK = ("Show the person this preview. When they agree, call {tool} again with exactly the same arguments and "
       "confirm=\"{token}\" (valid for {minutes} minutes). Nothing has changed yet.")


# ================================================================ preview, then confirm (D458)
def args_hash(tool: str, args: dict) -> str:
    """The arguments a confirm must repeat: everything but confirm and why, in a stable order."""
    kept = {k: v for k, v in (args or {}).items() if k not in ("confirm", "why")}
    return hashlib.sha256(json.dumps([tool, kept], sort_keys=True, default=str).encode()).hexdigest()


def _keep_preview(conn, user, tool: str, h: str, summary: dict) -> str:
    token = "pv_" + secrets.token_urlsafe(18)
    conn.execute(text("""INSERT INTO core.mcp_previews (token, username, tool, args_hash, summary, expires_at)
                         VALUES (:t, :u, :tool, :h, CAST(:s AS jsonb), now() + make_interval(mins => :m))"""),
                 {"t": token, "u": user.username.lower(), "tool": tool, "h": h, "s": json.dumps(_clean(summary))[:200000],
                  "m": PREVIEW_MINUTES})
    return token


def _use_preview(conn, user, tool: str, h: str, token: str) -> None:
    """The confirm must be this person's, for this tool and these arguments, not used and not expired."""
    row = conn.execute(text("""SELECT username, tool, args_hash, used_at, expires_at < now() AS expired
                                 FROM core.mcp_previews WHERE token = :t FOR UPDATE"""), {"t": token}).mappings().first()
    if not row:
        raise EditError("No such preview: call the tool without confirm first, show the person the preview, then confirm.", 409)
    if row["username"] != user.username.lower():
        raise EditError("This preview was made for someone else: preview it yourself first.", 403)
    if row["tool"] != tool or row["args_hash"] != h:
        raise EditError("The arguments differ from the preview's: preview again with these arguments.", 409)
    if row["used_at"] is not None:
        raise EditError("This preview was confirmed already: preview again to make another change.", 409)
    if row["expired"]:
        raise EditError(f"This preview is more than {PREVIEW_MINUTES} minutes old: preview again.", 409)
    conn.execute(text("UPDATE core.mcp_previews SET used_at = now() WHERE token = :t"), {"t": token})


async def operate(tool: str, args: dict, confirm: str, preview: Callable, apply: Callable,
                  tag: Callable | list | None = None, label: str = "") -> Any:
    """Runs a changing tool in two calls. preview(conn, user) -> what will happen (on a connection whose writes are
    never kept); apply(conn, user) -> what happened (one transaction, after the models from `tag` are tagged)."""
    user = permissions.current.get()
    if user is None:
        return {"error": "Sign in required."}
    if why := may_write():
        return {"error": why}
    h = args_hash(tool, args)
    eng = get_engine()

    def model_guid(conn) -> str | None:
        ref = args.get("model")
        if not ref:
            return None
        try:
            return str(repo.get_model(conn, ref)["id"])
        except Exception:  # noqa: BLE001 - a copy's source may be gone by then; citations only
            return None

    if not confirm:
        def work():
            with eng.connect() as conn:                     # nothing a preview writes is kept
                pv = preview(conn, user)
                g = model_guid(conn)
            with eng.begin() as conn:
                token = _keep_preview(conn, user, tool, h, pv if isinstance(pv, dict) else {"preview": pv})
            return pv, token, g
        try:
            pv, token, g = await anyio.to_thread.run_sync(work)
        except (repo.NotFound, EditError, PermissionError, ViewsDown) as exc:
            return {"error": str(exc)}
        note_call(previewed=True)
        return cite(_clean({"preview": pv, "confirm": token, "expires_in_minutes": PREVIEW_MINUTES,
                            "next": ASK.format(tool=tool, token=token, minutes=PREVIEW_MINUTES)}), g)

    def work_apply():
        with eng.begin() as conn:
            _use_preview(conn, user, tool, h, confirm)
            targets = tag(conn) if callable(tag) else (tag or [])
            tags = [tag_before(conn, user, t, f"{label or tool.replace('_', ' ')} (through MCP)") for t in targets if t]
            out = apply(conn, user)
            g = model_guid(conn)
            audit.record(conn, actor=user.username, action=f"mcp.{tool}", object_type="model", object_id=g or str(args.get("model") or ""),
                         details={"via": "mcp", "preview": confirm, "tags": [t["tag"] for t in tags],
                                  "why": str(args.get("why") or "")[:300]}, source="mcp")
            return out, tags, g
    try:
        out, tags, g = await anyio.to_thread.run_sync(work_apply)
    except (repo.NotFound, EditError, PermissionError, ViewsDown) as exc:
        return {"error": str(exc)}
    result = {"done": True, "tagged_first": tags, **(out if isinstance(out, dict) else {"result": out})}
    link = result.get("link") or (f"/#/metamodel/{g}" if g else "")
    note_call(wrote=True, changes=[{"what": label or tool.replace("_", " "), "model": str(args.get("model") or result.get("name") or ""),
                                    "link": link, "message": str(result.get("message") or "")[:300]}])
    return cite(_clean(result), g)


def _who():
    return permissions.current.get()


def _model_brief(m: dict) -> dict:
    return {"id": str(m["id"]), "name": m["name"], "kind": m["kind"], "entities": m.get("entity_count"),
            "parent": m.get("parent_model_name"), "frozen": bool(m.get("frozen_at")), "link": f"/#/metamodel/{m['id']}"}


# ================================================================ copy a model, or make a child
@mcp.tool()
async def copy_model(model: str, name: str, linked: bool = True, copy: str = "content", tag: str = "", description: str = "",
                     confirm: str = "", why: str = "") -> Any:
    """Make a copy of a model (D458). linked=true (the default) makes a CHILD: a copy linked to `model` that can later
    override it (override_parent) or be refreshed from it; linked=false a separate copy. copy="metamodel" copies the
    metamodel only; tag=<tag name or id> copies the model as it was then (separate copies only). Needs the right to
    create models. First call: a preview and a confirm token; call again with confirm=<token> to make it. Pass why: the
    person's request in a line."""
    args = {"model": model, "name": name, "linked": linked, "copy": copy, "tag": tag, "description": description}

    def preview(conn, user):
        src = repo.get_model(conn, model)
        if not permissions.allowed(user.roles, "models.create") and permissions.SUPER_ADMIN not in (user.roles or ()):
            raise EditError("Making a model needs the Model Creator role.", 403)
        if linked and src["kind"] != "project":
            raise EditError(f"{src['name']} is a {src['kind']} model: a linked copy (child) is made of a project model only. Use linked=false.")
        return {"will": f"Make {'a child of' if linked else 'a separate copy of'} {src['name']} called {name}"
                        + (" (metamodel only)" if copy == "metamodel" else f" with its {src.get('entity_count') or 0} entities")
                        + (f", as it was at tag {tag}" if tag else "") + ".",
                "source": _model_brief(src), "linked": linked,
                "then": "A child can be cleaned up (find_duplicates, merge_duplicates, change_entities) and then override its "
                        "parent (override_parent)." if linked else "A separate copy has no link back to the source."}
    return await operate("copy_model", args, confirm, preview,
                         lambda conn, user: copy_or_child(conn, user, model, name, linked, copy, description, tag),
                         label=f"copy of {model}")


# ================================================================ dedupe (phase 21)
@mcp.tool()
async def find_duplicates(model: str, entity_type: str = "", closeness: float = 0.88, attributes: list[str] | None = None,
                          by_name: bool = True) -> Any:
    """Likely duplicates in a model, in groups, each saying why (the same or close names, near spellings, words in another
    order; or, with attributes, the same values in all of them). closeness 0.6 to 1.0 (0.88 by default). Then decide per
    group which entity to keep (compare_duplicates shows each field side by side) and merge them with merge_duplicates."""
    from . import dedupe
    return await _run(lambda conn: dedupe.candidates(conn, model, entity_type or None, attributes or [], closeness, by_name))


@mcp.tool()
async def compare_duplicates(model: str, entities: list[str], keep: str = "") -> Any:
    """A pair or group of entities side by side: every field with each entity's value, which differ, and what merging into
    `keep` (default: the one with the most relationships and values) would move and drop."""
    from . import dedupe
    return await _run(lambda conn: dedupe.compare(conn, model, entities, keep or None))


@mcp.tool()
async def merge_duplicates(model: str, groups: list[dict], confirm: str = "", why: str = "") -> Any:
    """Merge duplicates "as you see fit" (D458): groups = [{keep: entity guid, others: [guids], choices: {field code: the
    guid whose value the kept one takes}}] (field codes as compare_duplicates gives them: name, description, parent,
    value:<attribute>). The others' relationships move to the one kept, repeats are dropped, the others go; old IDs still
    find it. Committed at once when the person may commit, else left as their changes. The model is tagged first.
    First call: a preview and a confirm token; call again with confirm=<token>."""
    from . import dedupe
    if not groups:
        return {"error": "Give at least one group: {keep, others, choices}."}
    args = {"model": model, "groups": groups}

    def preview(conn, user):
        m = repo.get_model(conn, model)
        dedupe._may_change(conn, user, m)
        out = []
        for g in groups:
            ids = [g.get("keep")] + [o for o in g.get("others") or [] if o != g.get("keep")]
            c = dedupe.compare(conn, model, ids, g.get("keep"))
            names = {e["id"]: e["name"] for e in c["entities"]}
            out.append({"keep": names.get(c["keep"]), "merged_into_it": [names[i] for i in ids[1:] if i in names],
                        "type": c["type"], "values_taken": {k: names.get(v, v) for k, v in (g.get("choices") or {}).items()},
                        "relationships_moved": len(c["moves"]), "repeats_dropped": c["dropped"]})
        return {"model": _model_brief(m), "groups": out,
                "will": f"Merge {sum(len(x['merged_into_it']) for x in out)} duplicates into {len(out)} entities in {m['name']}, "
                        "after tagging it."}

    def apply(conn, user):
        done = [dedupe.merge(conn, model, user, g["keep"], g.get("others") or [], g.get("choices")) for g in groups]
        return {"merged": sum(d["merged"] for d in done), "groups": done,
                "message": f"{sum(d['merged'] for d in done)} duplicates merged in {len(done)} groups."}
    return await operate("merge_duplicates", args, confirm, preview, apply, tag=[model], label="merging duplicates")


# ================================================================ merge into the parent (phases 19/20)
@mcp.tool()
async def override_parent(model: str, note: str = "", after: str = "none", confirm: str = "", why: str = "") -> Any:
    """The child `model` overrides its parent (D458, "override its parent with it"): its changes since its starting point
    are sent for merge, EVERY change is accepted (conflicts take the child's value: the copy overrides the parent) and
    merged into the parent as one commit. The child and the parent are tagged first. after: "none" (default), "freeze"
    (the child becomes final) or "refresh" (the child matches the parent again). Needs the Model Admin role on the child,
    and on the parent a reviewer role (Committer, Model Sub Admin or Model Admin; Model Admin when the metamodel grows).
    First call: a preview and a confirm token; call again with confirm=<token>."""
    from . import merge_back as mb
    if after not in ("none", "freeze", "refresh"):
        return {"error": "after is none, freeze or refresh."}
    args = {"model": model, "note": note, "after": after}

    def rights(conn, user):
        child = repo.get_model(conn, model)
        parent = mb._parent(conn, child)
        if not mb.is_reviewer(conn, user, parent):
            raise EditError(f"Overriding {parent['name']} needs the Committer, Model Sub Admin or Model Admin role on it.", 403)
        return child, parent

    def preview(conn, user):
        child, parent = rights(conn, user)
        p = mb.preview(conn, model, user)
        changes = p.get("changes") or []
        meta = [c for c in changes if c.get("kind") == "metamodel"]
        if meta and not mb.is_parent_admin(conn, user, parent):
            raise EditError(f"The override adds to the metamodel of {parent['name']}: that needs its Model Admin role.", 403)
        kinds: dict[str, int] = {}
        for c in changes:
            kinds[c.get("kind", "?")] = kinds.get(c.get("kind", "?"), 0) + 1
        return {"child": _model_brief(child), "parent": _model_brief(parent), "counts": p.get("counts"), "by_kind": kinds,
                "conflicts": sum(1 for c in changes if c.get("conflict")),
                "first_changes": [{k: c.get(k) for k in ("kind", "name", "entity_type", "field", "conflict")} for c in changes[:40]],
                "will": f"Merge every change of {child['name']} ({len(changes)}) into {parent['name']}, conflicts taking "
                        f"{child['name']}'s value; both tagged first" + ({"freeze": f"; then freeze {child['name']}",
                                                                           "refresh": f"; then refresh {child['name']} from {parent['name']}"}
                                                                          .get(after, "")) + "."}

    def apply(conn, user):
        rights(conn, user)
        return override(conn, user, model, note, after)
    return await operate("override_parent", args, confirm, preview, apply, tag=[model], label="overriding the parent")


@mcp.tool()
async def list_merge_requests(model: str = "") -> Any:
    """Merge requests: a model's (those it sent as a child and those sent to it as a parent), or with no model those
    waiting for you (to review, or to choose freeze or refresh)."""
    from . import merge_back as mb
    if model:
        return await _run(lambda conn: mb.listing(conn, model, _who()))
    return await _run(lambda conn: mb.waiting_for(conn, _who()))


@mcp.tool()
async def get_merge_request(request: str) -> Any:
    """One merge request with every change (kind, field, conflict, decision), the counts and the merge report: to
    summarise it and suggest a decision for each conflict (the person decides)."""
    from . import merge_back as mb
    return await _run(lambda conn: mb.get(conn, request, _who()))


@mcp.tool()
async def decide_merge_request(request: str, action: str, decisions: dict | None = None, note: str = "", confirm: str = "",
                               why: str = "") -> Any:
    """Act on a merge request as a reviewer or the child's Model Admin. action: "decide" (decisions {change id: {accept:
    true|false, reason}}; a rejection needs a reason), "merge" (everything accepted goes into the parent; tagged first),
    "withdraw", "freeze" or "refresh" (after the merge). First call: a preview and a confirm token; call again with
    confirm=<token>."""
    from . import merge_back as mb
    if action not in ("decide", "merge", "withdraw", "freeze", "refresh"):
        return {"error": "action is decide, merge, withdraw, freeze or refresh."}
    args = {"request": request, "action": action, "decisions": decisions or {}, "note": note}

    def preview(conn, user):
        r = mb.get(conn, request, user)
        return {"request": {k: r.get(k) for k in ("id", "number", "status", "child", "parent", "counts", "undecided", "rejected")},
                "action": action, "decisions": len(decisions or {}),
                "will": {"decide": f"Record {len(decisions or {})} decisions", "merge": "Merge everything accepted into the parent",
                         "withdraw": "Withdraw the request", "freeze": "Freeze the child", "refresh": "Refresh the child from the parent"}[action] + "."}

    def apply(conn, user):
        if action == "decide":
            return mb.decide(conn, request, user, decisions or {})
        if action == "merge":
            return mb.merge(conn, request, user)
        if action == "withdraw":
            return mb.withdraw(conn, request, user, note)
        return mb.finish(conn, request, user, action, note)
    return await operate("decide_merge_request", args, confirm, preview, apply, label=f"merge request: {action}")


@mcp.tool()
async def refresh_from_parent(model: str, confirm: str = "", why: str = "") -> Any:
    """The child `model` becomes what its parent is now (all content; the parent's metamodel parts are added, nothing of
    the child's metamodel taken away), as one commit, tagged first, with a new starting point. Needs the Model Admin
    role on the child. First call: a preview and a confirm token; call again with confirm=<token>."""
    from . import merge_back as mb
    args = {"model": model}

    def check(conn, user):
        child = repo.get_model(conn, model)
        parent = mb._parent(conn, child)
        if not mb.is_child_admin(conn, user, child):
            raise EditError(f"Refreshing {child['name']} needs the Model Admin role on it.", 403)
        return child, parent

    def preview(conn, user):
        child, parent = check(conn, user)
        return {"child": _model_brief(child), "parent": _model_brief(parent),
                "will": f"{child['name']} ({child.get('entity_count') or 0} entities) becomes what {parent['name']} is now "
                        f"({parent.get('entity_count') or 0} entities); what only the child has is removed (it is tagged first)."}

    def apply(conn, user):
        child, _parent = check(conn, user)
        return mb.refresh(conn, child, user)
    return await operate("refresh_from_parent", args, confirm, preview, apply, label="refreshing from the parent")


# ================================================================ the other model wizards
def _wizards() -> dict[str, dict]:
    """The model wizards MCP runs (name -> what it does, whether the model is tagged first, the call)."""
    from . import merge as mg
    from . import model_ops as mo
    from . import model_wizards as mw
    from . import pushdown as pd
    from . import tags as tg

    def propagate(conn, model, user, p):
        src = p.get("source")
        if not src:
            m = repo.get_model(conn, model)
            if not m.get("parent_model_id"):
                raise EditError(f"{m['name']} has no parent: give params.source, the model whose changes come in.")
            src = str(m["parent_model_id"])
        plan = mg.analyse_model(conn, model, src, user, p.get("with_data", True))
        return mg.apply(conn, model, plan["id"], user, None, p.get("conflicts") or "theirs", bool(p.get("add_metamodel", True)))

    def propagate_preview(conn, model, user, p):
        src = p.get("source")
        if not src:
            m = repo.get_model(conn, model)
            src = str(m["parent_model_id"]) if m.get("parent_model_id") else None
        if not src:
            raise EditError("Give params.source, the model whose changes come in.")
        plan = mg.analyse_model(conn, model, src, user, p.get("with_data", True))
        return {k: plan.get(k) for k in ("source_model", "counts", "summary", "metamodel") if k in plan} | {
            "conflicts": len(plan.get("conflicts") or []), "conflicts_take": p.get("conflicts") or "theirs"}

    def push_down(conn, model, user, p):
        mw._admin(conn, user, repo.get_model(conn, model), "Pushing the metamodel down")
        try:
            return pd.push(conn, model, user.username, p.get("mode") or "offered", bool(p.get("fill_defaults", True)), p.get("note", ""))
        except pd.PushError as exc:
            raise EditError(str(exc), 409) from exc

    return {
        "freeze": {"about": "Freeze the model: read only for good (params.note)", "tag": True,
                   "run": lambda c, m, u, p: mw.freeze(c, m, u, p.get("note", ""))},
        "unfreeze": {"about": "Unfreeze a frozen model (Super Admins only)", "tag": False, "run": lambda c, m, u, p: mw.unfreeze(c, m, u)},
        "archive": {"about": "Archive the model (it is kept, read only, out of lists)", "tag": True,
                    "run": lambda c, m, u, p: _brief(mo.set_lifecycle(c, m, True, u.username))},
        "bring_back": {"about": "Bring an archived model back", "tag": False,
                       "run": lambda c, m, u, p: _brief(mo.set_lifecycle(c, m, False, u.username))},
        "detach": {"about": "Detach a child from its parent (a model of its own)", "tag": True, "run": lambda c, m, u, p: mw.detach(c, m, u)},
        "reparent": {"about": "Move the model under another project model (params.parent)", "tag": True,
                     "run": lambda c, m, u, p: mw.reparent(c, m, u, p.get("parent"))},
        "split": {"about": "Part of the model into a new model (params: name, entity_types, entities, child true|false, move true|false)",
                  "tag": True, "run": lambda c, m, u, p: mw.split(c, m, u, p)},
        "extend_metamodel": {"about": "Add parts of another model's metamodel (params.source, plus entity_types, relationship_types, attributes picked)",
                             "tag": True, "run": lambda c, m, u, p: mw.extend_metamodel(c, m, u, p.get("source"), p),
                             "preview": lambda c, m, u, p: mw.extend_preview(c, m, p.get("source"))},
        "hand_over": {"about": "Hand the model over: Model Admins to add and remove (params: add, remove, owner)", "tag": False,
                      "run": lambda c, m, u, p: mw.hand_over(c, m, u, p.get("add") or [], p.get("remove") or [], p.get("owner"))},
        "push_down": {"about": "Push the metamodel down to the models below (params: mode forced|offered, note)", "tag": True,
                      "run": push_down, "preview": lambda c, m, u, p: pd.overview(c, m)},
        "propagate": {"about": "Bring another model's (by default the parent's) changes into this model (params: source, conflicts theirs|mine)",
                      "tag": True, "run": propagate, "preview": propagate_preview},
        "restore_tag": {"about": "Put the model back as it was at a tag (params.tag, params.note)", "tag": True,
                        "run": lambda c, m, u, p: tg.restore_tag(c, m, u, p.get("tag"), p.get("note", ""))},
    }


def _brief(m: dict) -> dict:
    return {"model": str(m["id"]), "name": m["name"], "lifecycle": m.get("lifecycle"), "message": f"{m['name']} is {m.get('lifecycle') or 'changed'}."}


@mcp.tool()
async def model_wizard(model: str, wizard: str, params: dict | None = None, confirm: str = "", why: str = "") -> Any:
    """Run one of the model wizards on a model, as the person (D458): freeze, unfreeze, archive, bring_back, detach,
    reparent, split, extend_metamodel, hand_over, push_down, propagate, restore_tag. Call with wizard="list" to see what
    each takes. Copying is copy_model, duplicates merge_duplicates, merging into the parent override_parent or
    decide_merge_request, tags tag_model, comparing compare_models. First call: a preview and a confirm token; call again
    with confirm=<token>; the model is tagged first where the wizard changes it."""
    w = _wizards()
    if wizard == "list":
        return {"wizards": [{"wizard": k, "about": v["about"], "tagged_first": v["tag"]} for k, v in w.items()]}
    if wizard not in w:
        return {"error": f"No wizard {wizard!r}: one of {', '.join(w)} (or list)."}
    spec, p = w[wizard], params or {}
    args = {"model": model, "wizard": wizard, "params": p}

    def preview(conn, user):
        m = repo.get_model(conn, model)
        out = {"model": _model_brief(m), "wizard": wizard, "about": spec["about"], "params": p,
               "tagged_first": spec["tag"], "will": f"{spec['about'].split(' (')[0]} on {m['name']}."}
        if spec.get("preview"):
            out["details"] = spec["preview"](conn, model, user, p)
        return out
    return await operate("model_wizard", args, confirm, preview, lambda conn, user: spec["run"](conn, model, user, p),
                         tag=[model] if spec["tag"] else None, label=f"model wizard: {wizard}")


@mcp.tool()
async def common_analysis(models: list[str], save_in: str = "", name: str = "", confirm: str = "", why: str = "") -> Any:
    """What two or more models have in common (matched like a comparison). Without save_in: the analysis, nothing kept.
    With save_in (a model) and name: the analysis is kept in that model, previewed first (confirm=<token> to keep it)."""
    from . import commons
    sides = [{"kind": "model", "id": m} for m in models or []]
    if len(sides) < 2:
        return {"error": "Give two or more models."}
    if not save_in:
        def analyse(conn):
            loaded = commons.load_sides(conn, sides)
            info = commons.fields_for(loaded)
            res = commons.analyse(loaded, commons.clean_settings(None, info, len(loaded)))
            return {k: (v[:200] if isinstance(v, list) else v) for k, v in res.items()}
        return await _run(analyse)
    args = {"models": models, "save_in": save_in, "name": name, "model": save_in}

    def preview(conn, user):
        return {"keep_in": save_in, "name": name or "Common analysis", "analysis": commons.preview(conn, sides)}
    return await operate("common_analysis", args, confirm, preview,
                         lambda conn, user: commons.create(conn, save_in, user, name or "Common analysis", sides),
                         label="common analysis kept")
