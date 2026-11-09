"""Collect data from people (WIZ-018, phase 16.3, D339).

A Model Admin asks people for their part of a model: the entity types to fill in, a note and a date. Each person is
told (a request in their bell, with a link that opens the model's Import and export tab with those types chosen). They
download the sheet, fill it in and upload it: the rows become their uncommitted changes, which they ask to be
committed; the Model Admin reviews them as any commit request. Nothing new to keep: the request is the notification,
the answer is the commit request.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text

from . import notify
from . import permissions as perms
from . import repository as repo
from .metamodel_edit import EditError


def people(conn, model: Any) -> list[dict]:
    """Everyone with a role on the model, and whether they may load data into it (a role that changes its content)."""
    m = repo.get_model(conn, model)
    rows = conn.execute(text("""SELECT username, array_agg(role ORDER BY role) AS roles FROM core.model_users
                                 WHERE model_id = :m GROUP BY username ORDER BY username"""), {"m": m["_id"]}).mappings().all()
    out = []
    for r in rows:
        roles = list(r["roles"] or []) if not isinstance(r["roles"], str) else [x for x in r["roles"].strip("{}").split(",") if x]
        out.append({"username": r["username"], "roles": roles, "may_load": perms.allowed([], "model.content", roles)})
    return out


def ask(conn, model: Any, user, d: dict) -> dict:
    """Sends the request to each person chosen: {types: [codes], people: [usernames], note, due (YYYY-MM-DD)}."""
    m = repo.get_model(conn, model)
    if not (perms.SUPER_ADMIN in (user.roles or []) or perms.MODEL_ADMIN in perms.model_roles(conn, user.username, m["id"])):
        raise EditError(f"Asking people for data needs the Model Admin role on {m['name']}.", 403)
    have = {r["code"]: r["name"] for r in conn.execute(text(
        "SELECT code, name FROM core.entity_types WHERE model_id = :m AND NOT is_deleted"), {"m": m["_id"]}).mappings()}
    types = [t for t in (d.get("types") or []) if t in have]
    if not types:
        raise EditError("Choose the entity types they fill in.")
    who = {p["username"]: p for p in people(conn, m["id"])}
    chosen = [str(u).lower() for u in d.get("people") or [] if str(u).strip()]
    if not chosen:
        raise EditError("Choose the people to ask.")
    due = str(d.get("due") or "").strip()[:10]
    if due:
        try:
            date.fromisoformat(due)
        except ValueError as exc:
            raise EditError("The date is YYYY-MM-DD.") from exc
    note = str(d.get("note") or "").strip()[:2000]
    names = ", ".join(have[t] for t in types)
    link = f"#/metamodel/{m['id']}/import?types={','.join(types)}&collect=1"
    sent, skipped = [], []
    for u in chosen:
        p = who.get(u)
        if not p or not p["may_load"]:
            skipped.append({"username": u, "why": "has no role that changes the content of the model: give them access first "
                                                  "(Model admin > Hand over, or the model's People tab)"})
            continue
        notify.create(conn, kind="data.requested", category="request", needs_action=True, model_id=m["_id"], actor=user.username,
                      recipients=[u], link=link,
                      title=f"{user.username} asks you to fill in {names} in {m['name']}" + (f" by {due}" if due else ""),
                      body=(note + "\n\n" if note else "") + "Open the link: download the sheet with the types already chosen, fill "
                           "it in, upload it and check the preview. The rows become your changes: ask for them to be committed "
                           "(Changes tab), and they are reviewed like any change.")
        sent.append(u)
    return {"sent": sent, "skipped": skipped, "types": types,
            "message": f"Asked {len(sent)} {'person' if len(sent) == 1 else 'people'} for {names}"
                       + (f" by {due}" if due else "") + "." + (f" {len(skipped)} not asked (no role to change the content)."
                                                                 if skipped else "")}
