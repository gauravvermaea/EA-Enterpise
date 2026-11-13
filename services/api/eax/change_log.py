"""Phase 9: the change log (D180), one row per action a person takes, in a database of its own.

The change log never slows the repository: nothing extra is written when people change things. It is filled from what
the repository writes anyway, shipped across in the background (ship(), run every few seconds by
`python -m eax.change_log` beside the API, and before the Change log screen reads):
  * history.row_versions: every entity, value, relationship, metamodel part and model change, from any route (screens,
    API, MCP, merges, restores); one log row per person, item and save, its fields gathered with old and new values;
    changes made with no person set (the installer, the seed) are left out
  * audit.events: the API's actions that are not a row change of their own (ACTIONS: a tag made, a gap analysis
    compared, a merge, a commit, a model locked, a role given...)
Rows are shipped once their transaction has finished (history and audit rows carry their transaction, 0015), so a
transaction that started earlier but finished later is never missed.

Where it lives: EAX_CHANGELOG_DB_URL (postgresql://user:password@host:port/database), in the schema
EAX_CHANGELOG_DB_SCHEMA (default changelog); empty means the repository's own database. ensure() creates the schema
and tables there.

Who sees what: everyone their own rows; a Model Admin every row of the models they administer; a Super Admin every
row. Only a Super Admin exports or deletes rows. Deleting log rows never touches the history, the History tab, roll
back or the audit trail; the deletion is logged.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import text

from . import permissions as perms
from .metamodel_edit import EditError

# API actions that are logged (label, item type); the others are either a row change the database logs already
# (entities, values, relationships, metamodel parts) or not a change at all (reads, downloads, queries)
ACTIONS: dict[str, tuple[str, str]] = {
    "tag.create": ("Tagged the model", "Tag"),
    "backup.infrastructure": ("Made an infrastructure backup", "Backup"),
    "backup.application": ("Made an application backup", "Backup"),
    "backup.model": ("Backed up the model", "Backup"),
    "backup.restore": ("Restored a model backup", "Backup"),
    "backup.restore.start": ("Started restoring an infrastructure backup", "Backup"),
    "backup.restore.done": ("An infrastructure restore finished", "Backup"),
    "backup.pin": ("Pinned or unpinned a backup", "Backup"),
    "backup.upload": ("Uploaded a model backup", "Backup"),
    "backup.cleanup": ("Removed old backups", "Backup"),
    "backup.scheduled": ("A scheduled backup ran", "Backup"),
    "backup.schedule": ("Changed a backup schedule", "Backup"),
    "backup.delete": ("Deleted a backup or a restore by hand", "Backup"),
    "tag.update": ("Changed a tag", "Tag"),
    "tag.delete": ("Deleted a tag", "Tag"),
    "tag.restore": ("Made a tag the latest", "Tag"),
    "gap.create": ("Made a gap analysis", "Gap analysis"),
    "gap.refresh": ("Compared a gap analysis again", "Gap analysis"),
    "gap.delete": ("Deleted a gap analysis", "Gap analysis"),
    "gap.run_delete": ("Deleted a gap analysis result", "Gap analysis"),
    "gap.item": ("Decided a gap", "Gap analysis"),
    "gap.items": ("Decided gaps", "Gap analysis"),
    "gap.entities": ("Added gaps as Gap entities", "Gap analysis"),
    "compare.profile_save": ("Saved a comparison profile", "Comparison profile"),
    "compare.profile_delete": ("Deleted a comparison profile", "Comparison profile"),
    "merge.apply": ("Merged into the model", "Model"),
    "changes.commit": ("Committed changes", "Commit"),
    "changes.request": ("Asked for changes to be committed", "Commit"),
    "changes.withdraw": ("Withdrew a commit request", "Commit"),
    "changes.reject": ("Rejected changes", "Commit"),
    "changes.send-back": ("Sent changes back", "Commit"),
    "changes.discard": ("Discarded uncommitted changes", "Commit"),
    "commit.roll_back": ("Rolled back a commit", "Commit"),
    "model.created": ("Created a model", "Model"),
    "model.copied": ("Copied a model", "Model"),
    "model.deleted": ("Deleted a model", "Model"),
    "model.lock": ("Locked the model", "Model"),
    "model.unlock": ("Unlocked the model", "Model"),
    "model.archived": ("Archived the model", "Model"),
    "model.reactivated": ("Reactivated the model", "Model"),
    "model.framework_moved": ("Moved the model to another framework", "Model"),
    "model.publish_requested": ("Requested publishing", "Model"),
    "model.publish_request_withdrawn": ("Withdrew a publishing request", "Model"),
    "model.published": ("Published the model", "Model"),
    "model.publish_sent_back": ("Sent the model back", "Model"),
    "model.publish_rejected": ("Rejected the model", "Model"),
    "model.reopened": ("Opened the model again", "Model"),
    "model.role": ("Gave a role on the model", "Role"),
    "model.unassign": ("Removed a role on the model", "Role"),
    "package.uploaded": ("Uploaded a model package", "Model"),
    "load.upload": ("Uploaded a sheet to load", "Load"),
    "load.added": ("Loaded a sheet: its rows became changes", "Load"),
    "load.undo": ("Undid a load", "Load"),
    "load.delete": ("Deleted a load", "Load"),
    "request.send": ("Sent a request", "Request"),
    "request.status": ("Moved a request along", "Request"),
    "notification.resolve": ("Resolved a notification", "Notification"),
    "pushdown.push": ("Pushed metamodel changes to the models below", "Metamodel"),
    "pushdown.accepted": ("Accepted metamodel changes from the parent", "Metamodel"),
    "pushdown.rejected": ("Rejected metamodel changes from the parent", "Metamodel"),
    "webhook.add": ("Added a webhook", "Webhook"),
    "container.exec": ("Ran a command in a container", "Container"),
    "container.terminal.open": ("Opened a terminal in a container", "Container"),
    "container.terminal.close": ("A terminal in a container ended", "Container"),
    "remote.ssh.open": ("An SSH session to a remote instance's host opened", "Remote instance"),
    "remote.ssh.close": ("An SSH session to a remote instance's host ended", "Remote instance"),
    "webhook.change": ("Changed a webhook", "Webhook"),
    "webhook.delete": ("Deleted a webhook", "Webhook"),
    "library.promoted": ("Promoted to the library", "Model"),
    "library.withdrawn": ("Withdrew from the library", "Model"),
    "library.restored": ("Restored to the library", "Model"),
    "draft.created": ("Made a metamodel draft", "Metamodel draft"),
    "draft.applied": ("Applied a metamodel draft", "Metamodel draft"),
    "draft.rejected": ("Rejected a metamodel draft", "Metamodel draft"),
    "draft.sent_back": ("Sent a metamodel draft back", "Metamodel draft"),
    "draft.reopened": ("Opened a metamodel draft again", "Metamodel draft"),
    "draft.resubmitted": ("Resubmitted a metamodel draft", "Metamodel draft"),
    "view.save": ("Saved a view", "Saved view"),
    "view.delete": ("Deleted a view", "Saved view"),
    "viewpoint.add": ("Added a view", "View"),
    "viewpoint.change": ("Changed a view", "View"),
    "viewpoint.delete": ("Deleted a view", "View"),
    "settings.change": ("Changed settings", "Settings"),
    "system.restart": ("Restarted the system", "System"),
    "system.service": ("Switched a service on or off", "System"),
    "system.config_restore": ("Restored a copy of the config file", "System"),
    "role-mapping.add": ("Mapped a Keycloak role", "Role mapping"),
    "role-mapping.remove": ("Removed a Keycloak role mapping", "Role mapping"),
    # surveys and maturity assessments (phases 38.1 and 40): who did what, never what anyone answered
    "survey.create": ("Made a survey", "Survey"),
    "survey.update": ("Changed a survey", "Survey"),
    "survey.delete": ("Deleted a draft survey", "Survey"),
    "survey.copy": ("Copied a survey", "Survey"),
    "survey.send": ("Sent a survey", "Survey"),
    "survey.recipients": ("Asked more people in a survey", "Survey"),
    "survey.remind": ("Reminded people to answer a survey", "Survey"),
    "survey.close": ("Closed a survey", "Survey"),
    "survey.reopen": ("Reopened a survey", "Survey"),
    "survey.answer": ("Answered a survey", "Survey"),
    "maturity.create": ("Started a maturity assessment", "Survey"),
    # machine access (phase 25, D366): every call made with a credential, and the credentials themselves
    "machine.call": ("Called the API with a credential", "Machine access"),
    "machine.credential.create": ("Made a credential", "Machine access"),
    "machine.credential.change": ("Changed a credential", "Machine access"),
    "machine.credential.revoke": ("Revoked a credential", "Machine access"),
    "machine.service_account.create": ("Made a service account", "Service account"),
    "machine.service_account.change": ("Changed a service account", "Service account"),
    # housekeeping (phase 35.1, D371)
    "housekeeping.rule": ("Changed a retention rule", "Housekeeping"),
    "housekeeping.dry_run": ("Did a housekeeping dry run", "Housekeeping"),
    "housekeeping.confirm": ("Confirmed a housekeeping dry run", "Housekeeping"),
    "housekeeping.run": ("Housekeeping archived or deleted old records", "Housekeeping"),
    "housekeeping.history_removed": ("Housekeeping removed old history versions", "Housekeeping"),
    # ADM iteration types (D571-D574)
    "project.iteration": ("Changed a project's ADM iteration", "Project"),
}
NAME_KEYS = ("name", "tag", "analysis_name", "title", "username", "keycloak_role", "message", "note", "number")
KINDS = {"content": "Content", "metamodel": "Metamodel", "model": "Model", "action": "Action"}
LIMIT = 200


def _as_uuid(v: Any) -> str | None:
    try:
        return str(uuid.UUID(str(v)))
    except (ValueError, TypeError, AttributeError):
        return None


def _jsonable(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return ", ".join(str(_jsonable(x)) for x in v[:20]) + (f" (+{len(v) - 20})" if len(v) > 20 else "")
    if isinstance(v, dict):
        return json.dumps(v, default=str)[:300]
    return str(v)


# ---------------------------------------------------------------- the change log's own database
TECH = {"id", "guid", "model_id", "row_version", "created_at", "created_by", "modified_at", "modified_by", "created_mm_version",
        "modified_mm_version", "origin_guid", "is_deleted", "updated_at", "updated_by", "deleted_at", "deleted_by",
        "metamodel_version", "entity_count", "relationship_count", "sort_order", "tx"}
TYPES = {"entities": "Entity", "relationships": "Relationship", "attribute_values": "Entity", "models": "Model", "layers": "Domain",
         "entity_types": "Entity type", "relationship_types": "Relationship type", "pick_lists": "Pick list",
         "pick_list_values": "Pick list value", "attribute_types": "Attribute", "item_attributes": "Attribute of a type",
         "validation_rules": "Rule", "allowed_relationships": "Allowed relationship"}
ENTITY_FIELDS = {"name": "Name", "display_id": "Display ID", "description": "Description", "status_code": "Status",
                 "parent_entity_id": "Parent", "tags": "Tags", "entity_type_id": "Type"}
BATCH = 2000


def schema() -> str:
    from .config import get_settings
    name = get_settings().changelog_db_schema or "changelog"
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name):
        raise ValueError(f"EAX_CHANGELOG_DB_SCHEMA must be a plain lower-case name, not {name!r}")
    return name


_ENSURED: set[str] = set()


def ensure(cl, again: bool = False) -> None:
    """Creates the change log's schema and tables in its database when they are missing (safe on every start). Done once
    per process and database (R2.0.1): CREATE ... IF NOT EXISTS still takes table locks, so running it on every read made
    the change log's screen wait behind the shipper when many asked at once."""
    try:
        key = f"{cl.engine.url.render_as_string(hide_password=True)}|{schema()}"
    except AttributeError:   # not a real connection (the unit tests' fakes): always run
        key, again = "", True
    if key in _ENSURED and not again:
        return
    _do_ensure(cl)
    _ENSURED.add(key)


def _do_ensure(cl) -> None:
    s = schema()
    cl.execute(text(f"""
        CREATE SCHEMA IF NOT EXISTS {s};
        CREATE TABLE IF NOT EXISTS {s}.entries (
            id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            at          timestamptz NOT NULL,
            username    text        NOT NULL,
            model_id    bigint,
            model_guid  uuid,
            model_name  text,
            kind        text        NOT NULL,
            action      text        NOT NULL,
            item_type   text        NOT NULL,
            item_guid   uuid,
            item_key    text        NOT NULL DEFAULT '',
            item_name   text,
            entity_type text,
            details     jsonb       NOT NULL DEFAULT '[]',
            source      text        NOT NULL,
            source_id   bigint
        );
        CREATE UNIQUE INDEX IF NOT EXISTS entries_action_idx ON {s}.entries (at, username, item_type, item_key) WHERE source = 'data';
        CREATE UNIQUE INDEX IF NOT EXISTS entries_api_idx ON {s}.entries (source_id) WHERE source = 'api';
        CREATE INDEX IF NOT EXISTS entries_at_idx ON {s}.entries (at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS entries_user_idx ON {s}.entries (lower(username), at DESC);
        CREATE INDEX IF NOT EXISTS entries_model_idx ON {s}.entries (model_id, at DESC);
        CREATE TABLE IF NOT EXISTS {s}.shipped (
            source  text PRIMARY KEY,           -- history | audit
            tx      bigint NOT NULL DEFAULT 0,  -- the last row shipped: its transaction and id
            id      bigint NOT NULL DEFAULT 0,
            at      timestamptz NOT NULL DEFAULT now()
        );
        INSERT INTO {s}.shipped (source) VALUES ('history'), ('audit') ON CONFLICT DO NOTHING;
        ALTER TABLE {s}.entries ADD COLUMN IF NOT EXISTS commit_number integer;   -- the commit it came in with (D195)
        ALTER TABLE {s}.entries ADD COLUMN IF NOT EXISTS commit_message text;
    """))


def _logins() -> set[str]:
    from .config import get_settings
    st = get_settings()
    return {x.lower() for x in (st.db_user, st.db_migrator_user, "postgres", "eax_report", "eax_app", "eax_migrator", "") if x is not None}


def _rows(conn, sql: str, **p) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), p).mappings()]


def _txt(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) or None
    if isinstance(v, (dict,)):
        return json.dumps(v, default=str)
    return str(v)


def _value(d: dict | None, names: dict) -> str | None:
    if not d or d.get("is_deleted"):
        return None
    for k in ("value_text", "value_number", "value_date", "value_bool"):
        if d.get(k) is not None:
            return str(d[k])
    ref = d.get("value_ref")
    return names["entity"].get(int(ref), {}).get("name") if ref is not None else None


def _lookups(conn, rows: list[dict]) -> dict:
    """Names the batch needs, read in a few queries: entities, types, attributes, models."""
    want: dict[str, set[int]] = {"entity": set(), "etype": set(), "rtype": set(), "attr": set(), "model": set(), "rel": set()}
    for r in rows:
        for d in (r["data"], r.get("prev") or {}):
            for k, b in (("entity_id", "entity"), ("parent_entity_id", "entity"), ("value_ref", "entity"), ("source_entity_id", "entity"),
                         ("target_entity_id", "entity"), ("entity_type_id", "etype"), ("source_type_id", "etype"),
                         ("target_type_id", "etype"), ("relationship_type_id", "rtype"), ("attribute_type_id", "attr"),
                         ("relationship_id", "rel")):
                if d.get(k) is not None:
                    want[b].add(int(d[k]))
        if r.get("model_id") is not None:
            want["model"].add(int(r["model_id"]))

    def get(sql: str, ids: set[int]) -> dict[int, dict]:
        return {x["id"]: x for x in _rows(conn, sql, ids=list(ids))} if ids else {}
    return {
        "entity": get("""SELECT e.id, e.guid, e.name, t.name AS type_name FROM core.entities e JOIN core.entity_types t ON t.id = e.entity_type_id
                          WHERE e.id = ANY (CAST(:ids AS bigint[]))""", want["entity"]),
        "etype": get("SELECT id, name FROM core.entity_types WHERE id = ANY (CAST(:ids AS bigint[]))", want["etype"]),
        "rtype": get("SELECT id, name, verb FROM core.relationship_types WHERE id = ANY (CAST(:ids AS bigint[]))", want["rtype"]),
        "attr": get("SELECT id, name FROM core.attribute_types WHERE id = ANY (CAST(:ids AS bigint[]))", want["attr"]),
        "model": get("SELECT id, guid, name FROM core.models WHERE id = ANY (CAST(:ids AS bigint[]))", want["model"]),
        "rel": get("SELECT id, guid, name FROM core.relationships WHERE id = ANY (CAST(:ids AS bigint[]))", want["rel"]),
    }


def _nm(names: dict, bucket: str, key: Any, field: str = "name") -> Any:
    return (names[bucket].get(int(key)) or {}).get(field) if key is not None else None


def entry_of(r: dict, names: dict) -> dict | None:
    """One history row as a change log entry (or None: nothing a person would call a change). Same rules as before
    the change log moved out: values belong to their entity, technical fields never count."""
    t, new, old, op = r["table_name"], r["data"] or {}, r.get("prev"), r["operation"]
    kind = "content" if t in ("entities", "relationships", "attribute_values") else "model" if t == "models" else "metamodel"
    item_type = TYPES.get(t, t.replace("_", " ").capitalize())
    was_del, is_del = bool((old or {}).get("is_deleted")), bool(new.get("is_deleted"))
    action = ("Created" if op == "insert" else "Deleted" if op == "delete" or (is_del and not was_del)
              else "Restored" if was_del and not is_del else "Changed")
    item, name, etype, details = str(r["row_guid"]), new.get("name") or new.get("label") or new.get("value") or new.get("code"), None, []
    if t == "attribute_values":
        o = None if op == "insert" or old is None else _value(old, names)
        n = None if op == "delete" else _value(new, names)
        if o == n:
            return None
        details = [{"field": _nm(names, "attr", new.get("attribute_type_id")) or "Value", "old": o, "new": n}]
        action = "Changed"
        if new.get("entity_id") is not None:
            e = names["entity"].get(int(new["entity_id"])) or {}
            item, name, etype = str(e.get("guid") or ""), e.get("name"), e.get("type_name")
        else:
            rel = names["rel"].get(int(new.get("relationship_id") or 0)) or {}
            item, name, item_type = str(rel.get("guid") or ""), rel.get("name"), "Relationship"
    elif t == "entities":
        etype = _nm(names, "etype", new.get("entity_type_id"))
        if action == "Changed" and old is not None:
            for k, label in ENTITY_FIELDS.items():
                if old.get(k) != new.get(k):
                    o, n = _txt(old.get(k)), _txt(new.get(k))
                    if k == "parent_entity_id":
                        o, n = _nm(names, "entity", old.get(k)), _nm(names, "entity", new.get(k))
                    elif k == "entity_type_id":
                        o, n = _nm(names, "etype", old.get(k)), etype
                    details.append({"field": label, "old": o, "new": n})
            if not details:
                return None
    elif t == "relationships":
        rt = names["rtype"].get(int(new.get("relationship_type_id") or 0)) or {}
        etype = rt.get("name")
        name = " ".join(x for x in (_nm(names, "entity", new.get("source_entity_id")), rt.get("verb") or rt.get("name"),
                                    _nm(names, "entity", new.get("target_entity_id"))) if x)
        action = {"Created": "Added", "Deleted": "Removed"}.get(action, action)
        if action == "Changed":
            if old is None or old.get("name") == new.get("name"):
                return None
            details = [{"field": "Name", "old": old.get("name"), "new": new.get("name")}]
    else:
        if t == "allowed_relationships":
            name = " ".join(x for x in (_nm(names, "etype", new.get("source_type_id")), _nm(names, "rtype", new.get("relationship_type_id")),
                                        _nm(names, "etype", new.get("target_type_id"))) if x)
        elif t == "item_attributes":
            name = " of ".join(x for x in (_nm(names, "attr", new.get("attribute_type_id")), _nm(names, "etype", new.get("entity_type_id")),
                                           _nm(names, "rtype", new.get("relationship_type_id"))) if x)
        if action == "Changed" and old is not None:
            for k in sorted(new):
                if k not in TECH and old.get(k) != new.get(k):
                    label = re.sub(r"_(id|code)$", "", k).replace("_", " ").capitalize()
                    details.append({"field": label, "old": _txt(old.get(k)), "new": _txt(new.get(k))})
            if not details:
                return None
    m = names["model"].get(int(r["model_id"])) if r.get("model_id") is not None else None
    return {"at": r["changed_at"], "username": str(r["changed_by"]).lower(), "model_id": r.get("model_id"),
            "model_guid": str(m["guid"]) if m else None, "model_name": m["name"] if m else None, "kind": kind, "action": action,
            "item_type": item_type, "item_guid": item or None, "item_key": item or "", "item_name": name, "entity_type": etype,
            "details": details, "source": "data", "source_id": None,
            "commit_number": (r.get("commit") or {}).get("number"), "commit_message": (r.get("commit") or {}).get("message")}


def _merge(a: dict, b: dict) -> dict:
    """Two entries of one action (same person, item and save): fields gathered; Created stays Created, Deleted wins."""
    a["details"] = a["details"] + b["details"]
    a["item_name"] = b["item_name"] or a["item_name"]
    if b["action"] in ("Deleted", "Removed"):
        a["action"] = b["action"]
    elif a["action"] not in ("Created", "Added") and b["action"] != "Changed":
        a["action"] = b["action"]
    return a


def _audit_entry(r: dict, models: dict) -> dict | None:
    if r["action"] not in ACTIONS or not r["actor"] or str(r["actor"]).lower() in _logins():
        return None
    label, item_type = ACTIONS[r["action"]]
    d = r["details"] if isinstance(r["details"], dict) else json.loads(r["details"] or "{}")
    name = next((str(d[k]) for k in NAME_KEYS if d.get(k) not in (None, "")), None)
    fields = [{"field": k.replace("_", " ").capitalize(), "old": None, "new": _jsonable(v)}
              for k, v in d.items() if v not in (None, "", [], {})][:12]
    m = models.get(_as_uuid(r["object_id"])) if (r["object_type"] or "") == "model" else None
    return {"at": r["at"], "username": str(r["actor"]).lower(), "model_id": m["id"] if m else None,
            "model_guid": str(m["guid"]) if m else None, "model_name": m["name"] if m else None, "kind": "action", "action": label,
            "item_type": item_type, "item_guid": None, "item_key": "", "item_name": name, "entity_type": None, "details": fields,
            "source": "api", "source_id": r["id"]}


def _write(cl, entries: list[dict]) -> None:
    s = schema()
    for e in entries:
        p = {**e, "details": json.dumps(e["details"], default=str)}
        if e["source"] == "data":
            cl.execute(text(f"""
                INSERT INTO {s}.entries (at, username, model_id, model_guid, model_name, kind, action, item_type, item_guid, item_key,
                                         item_name, entity_type, details, source, commit_number, commit_message)
                VALUES (:at, :username, :model_id, CAST(:model_guid AS uuid), :model_name, :kind, :action, :item_type,
                        CAST(:item_guid AS uuid), :item_key, :item_name, :entity_type, CAST(:details AS jsonb), 'data',
                        :commit_number, :commit_message)
                ON CONFLICT (at, username, item_type, item_key) WHERE source = 'data' DO UPDATE
                   SET details = {s}.entries.details || EXCLUDED.details,
                       commit_number = coalesce(EXCLUDED.commit_number, {s}.entries.commit_number),
                       commit_message = coalesce(EXCLUDED.commit_message, {s}.entries.commit_message),
                       item_name = coalesce(EXCLUDED.item_name, {s}.entries.item_name),
                       action = CASE WHEN EXCLUDED.action IN ('Deleted', 'Removed') THEN EXCLUDED.action
                                     WHEN {s}.entries.action IN ('Created', 'Added') THEN {s}.entries.action
                                     WHEN EXCLUDED.action = 'Changed' THEN {s}.entries.action ELSE EXCLUDED.action END"""), p)
        else:
            cl.execute(text(f"""
                INSERT INTO {s}.entries (at, username, model_id, model_guid, model_name, kind, action, item_type, item_name, details,
                                         source, source_id)
                VALUES (:at, :username, :model_id, CAST(:model_guid AS uuid), :model_name, :kind, :action, :item_type, :item_name,
                        CAST(:details AS jsonb), 'api', :source_id)
                ON CONFLICT (source_id) WHERE source = 'api' DO NOTHING"""), p)


def ship(conn, cl, limit: int = 50_000) -> int:
    """Ships the history and audit rows of finished transactions to the change log (at most `limit` rows a call).
    `conn` reads the repository with nobody signed in; `cl` writes the change log (its own transaction). Only one
    shipper works at a time (an advisory lock in the change log's database); the others return at once."""
    s = schema()
    if not cl.execute(text("SELECT pg_try_advisory_xact_lock(hashtext('eax.change_log.ship'))")).scalar():
        return 0
    upto = int(conn.execute(text("SELECT pg_snapshot_xmin(pg_current_snapshot())::text::bigint")).scalar())
    logins, done = _logins(), 0
    wm = {r["source"]: r for r in _rows(cl, f"SELECT source, tx, id FROM {s}.shipped")}
    while done < limit:
        w = wm["history"]
        rows = _rows(conn, """
            SELECT v.id, v.tx, v.table_name, v.row_id, v.row_guid, v.model_id, v.operation, v.data, v.changed_at, v.changed_by,
                   (SELECT p.data FROM history.row_versions p WHERE p.table_name = v.table_name AND p.row_id = v.row_id AND p.id < v.id
                     ORDER BY p.id DESC LIMIT 1) AS prev
              FROM history.row_versions v
             WHERE (v.tx, v.id) > (:tx, :id) AND v.tx < :upto
             ORDER BY v.tx, v.id LIMIT :n""", tx=w["tx"], id=w["id"], upto=upto, n=BATCH)
        if not rows:
            break
        for r in rows:
            for k in ("data", "prev"):
                if isinstance(r[k], str):
                    r[k] = json.loads(r[k])
        people = [r for r in rows if r["changed_by"] and str(r["changed_by"]).lower() not in logins]
        names = _lookups(conn, people) if people else {}
        txs = list({r["tx"] for r in people})
        commits = {(c["tx"], c["model_id"]): c for c in _rows(conn, """SELECT tx, model_id, number, message FROM core.commits
                                                                          WHERE tx = ANY (CAST(:t AS bigint[]))""", t=txs)} if txs else {}
        for r in people:
            r["commit"] = commits.get((r["tx"], r.get("model_id")))
        grouped: dict[tuple, dict] = {}
        for r in people:
            e = entry_of(r, names)
            if e is None:
                continue
            key = (e["at"], e["username"], e["item_type"], e["item_key"])
            grouped[key] = _merge(grouped[key], e) if key in grouped else e
        _write(cl, list(grouped.values()))
        last = rows[-1]
        wm["history"] = {"source": "history", "tx": last["tx"], "id": last["id"]}
        cl.execute(text(f"UPDATE {s}.shipped SET tx = :tx, id = :id, at = now() WHERE source = 'history'"), {"tx": last["tx"], "id": last["id"]})
        done += len(rows)
        if len(rows) < BATCH:
            break
    while done < limit:
        w = wm["audit"]
        rows = _rows(conn, """SELECT id, tx, at, actor, action, object_type, object_id, details FROM audit.events
                               WHERE (tx, id) > (:tx, :id) AND tx < :upto ORDER BY tx, id LIMIT :n""",
                     tx=w["tx"], id=w["id"], upto=upto, n=BATCH)
        if not rows:
            break
        keep = [r for r in rows if r["action"] in ACTIONS]
        guids = list({g for g in (_as_uuid(r["object_id"]) for r in keep) if g})
        models = {str(m["guid"]): m for m in _rows(conn, "SELECT id, guid, name FROM core.models WHERE guid = ANY (CAST(:g AS uuid[]))",
                                                   g=guids)} if guids else {}
        _write(cl, [e for e in (_audit_entry(r, models) for r in keep) if e])
        last = rows[-1]
        wm["audit"] = {"source": "audit", "tx": last["tx"], "id": last["id"]}
        cl.execute(text(f"UPDATE {s}.shipped SET tx = :tx, id = :id, at = now() WHERE source = 'audit'"), {"tx": last["tx"], "id": last["id"]})
        done += len(rows)
        if len(rows) < BATCH:
            break
    return done


def ship_now(limit: int = 50_000) -> int:
    """ship() with its own connections: the repository read with nobody signed in, the change log in one transaction."""
    from .db import get_changelog_engine, get_engine
    token = perms.current.set(None)
    try:
        with get_engine().connect() as conn, get_changelog_engine().connect() as cl:
            with cl.begin():
                ensure(cl)
            with cl.begin():
                return ship(conn, cl, limit)
    finally:
        perms.current.reset(token)


def clean_up() -> int:
    """Removes entries older than the keep period set in the administration console (phase 10: change_log_keep_days,
    0 keeps them for ever). The history and the audit trail are untouched."""
    from . import settings as app_settings
    from .db import get_changelog_engine
    days = int(app_settings.values().get("change_log_keep_days") or 0)
    if days <= 0:
        return 0
    with get_changelog_engine().connect() as cl, cl.begin():
        return cl.execute(text(f"DELETE FROM {schema()}.entries WHERE at < now() - make_interval(days => :d)"), {"d": days}).rowcount


def main() -> int:
    """`python -m eax.change_log`: ships every few seconds beside the API (entrypoint.sh), and removes entries past their
    keep period every hour; never stops on an error."""
    every, last_clean = 5.0, 0.0
    print("EA Explorer: change log shipper started", flush=True)
    while True:
        try:
            n = ship_now()
            if n:
                print(f"EA Explorer change log: shipped {n} rows", flush=True)
            if time.monotonic() - last_clean > 3600:
                last_clean = time.monotonic()
                gone = clean_up()
                if gone:
                    print(f"EA Explorer change log: removed {gone} entries past their keep period", flush=True)
        except Exception as exc:  # noqa: BLE001 - logged and tried again: the change log must never stop the API
            print(f"EA Explorer change log WARNING: {exc}", file=sys.stderr, flush=True)
            time.sleep(25)
        time.sleep(every)


# ---------------------------------------------------------------- reading
def _is_super(user) -> bool:
    return perms.SUPER_ADMIN in (getattr(user, "roles", None) or [])


def scope(conn, user) -> dict:
    """What this person may see: every row (Super Admin), or their own and those of the models they administer."""
    if _is_super(user):
        return {"all": True, "models": []}
    rows = conn.execute(text("""SELECT m.id, m.guid, m.name FROM core.model_users u JOIN core.models m ON m.id = u.model_id
                                 WHERE u.username = lower(:u) AND u.role = 'model-admin' ORDER BY m.name"""),
                        {"u": user.username}).mappings().all()
    return {"all": False, "models": [dict(r) for r in rows]}


def _where(user, sc: dict, f: dict) -> tuple[str, dict]:
    sql, p = [], {"me": user.username.lower()}
    if not sc["all"]:
        ids = [r["id"] for r in sc["models"]]
        p["admin"] = ids or [0]
        sql.append("(lower(l.username) = :me OR l.model_id = ANY (CAST(:admin AS bigint[])))")
    if f.get("mine"):
        sql.append("lower(l.username) = :me")
    if f.get("model"):
        p["model"] = str(f["model"])
        sql.append("l.model_guid = CAST(:model AS uuid)")
    if f.get("user"):
        p["user"] = str(f["user"]).strip().lower()
        sql.append("lower(l.username) = :user")
    if f.get("kind") in KINDS:
        p["kind"] = f["kind"]
        sql.append("l.kind = :kind")
    if f.get("action"):
        p["action"] = str(f["action"])
        sql.append("l.action = :action")
    if f.get("item_type"):
        p["item_type"] = str(f["item_type"])
        sql.append("l.item_type = :item_type")
    if f.get("from"):
        p["from"] = str(f["from"])[:10]
        sql.append("l.at >= CAST(:from AS date)")
    if f.get("to"):
        p["to"] = str(f["to"])[:10]
        sql.append("l.at < CAST(:to AS date) + 1")
    if f.get("q"):
        p["q"] = f"%{str(f['q']).strip().lower()}%"
        sql.append("""(lower(coalesce(l.item_name, '')) LIKE :q OR lower(coalesce(l.model_name, '')) LIKE :q
                      OR lower(l.username) LIKE :q OR lower(l.action) LIKE :q OR lower(l.details::text) LIKE :q)""")
    return (" AND ".join(sql) or "true"), p


def describe(r: dict) -> str:
    """One line for the row: what was done to what, and the fields changed."""
    what = f"{r['action']} {r['item_type'].lower()}" if r["source"] == "data" else r["action"]
    name = f" '{r['item_name']}'" if r.get("item_name") else ""
    fields = r.get("details") or []
    if r["source"] == "data" and fields:
        bits = [f"{d['field']}: {d.get('old') if d.get('old') is not None else '-'} -> {d.get('new') if d.get('new') is not None else '-'}"
                for d in fields[:3]]
        more = f" (+{len(fields) - 3} more)" if len(fields) > 3 else ""
        return f"{what}{name}: " + "; ".join(bits) + more
    return f"{what}{name}"


def _link(r: dict) -> str | None:
    if not r.get("model_guid"):
        return None
    if r["item_type"] == "Entity" and r.get("item_guid") and r["action"] != "Deleted":
        return f"#/metamodel/{r['model_guid']}/entity/{r['item_guid']}"
    return f"#/metamodel/{r['model_guid']}"


def _out(r: dict) -> dict:
    d = dict(r)
    for k in ("model_guid", "item_guid"):
        d[k] = str(d[k]) if d.get(k) else None
    d["details"] = d.get("details") if isinstance(d.get("details"), list) else json.loads(d.get("details") or "[]")
    d["summary"] = describe(d)
    d["link"] = _link(d)
    d["kind_name"] = KINDS.get(d["kind"], d["kind"])
    return d


COLS = """l.id, l.at, l.username, l.model_guid, l.model_name, l.kind, l.action, l.item_type, l.item_guid, l.item_name,
          l.entity_type, l.details, l.source, l.commit_number, l.commit_message"""


def entries(conn, user, f: dict | None = None, limit: int = LIMIT, offset: int = 0, cl=None) -> dict:
    """The change log as this person may see it, newest first, filtered; with totals and the choices for the filters.
    `conn` is the repository (who administers which model), `cl` the change log's database."""
    cl = cl if cl is not None else conn
    T = f"{schema()}.entries"
    f = f or {}
    sc = scope(conn, user)
    where, p = _where(user, sc, f)
    limit = max(1, min(int(limit or LIMIT), 1000))
    rows = cl.execute(text(f"SELECT {COLS} FROM {T} l WHERE {where} ORDER BY l.at DESC, l.id DESC "
                             "LIMIT :limit OFFSET :offset"), {**p, "limit": limit, "offset": max(0, int(offset or 0))}).mappings().all()
    total = cl.execute(text(f"SELECT count(*) FROM {T} l WHERE {where}"), p).scalar() or 0
    base, bp = _where(user, sc, {})
    def col(sql: str) -> list[dict]:
        return [dict(r) for r in cl.execute(text(sql), bp).mappings()]
    facets = {
        "users": [r["v"] for r in col(f"SELECT DISTINCT lower(l.username) AS v FROM {T} l WHERE {base} ORDER BY 1")],
        "models": [{"id": str(r["g"]), "name": r["n"]} for r in col(
            f"SELECT DISTINCT l.model_guid AS g, l.model_name AS n FROM {T} l WHERE {base} AND l.model_guid IS NOT NULL ORDER BY 2")],
        "actions": [r["v"] for r in col(f"SELECT DISTINCT l.action AS v FROM {T} l WHERE {base} ORDER BY 1")],
        "item_types": [r["v"] for r in col(f"SELECT DISTINCT l.item_type AS v FROM {T} l WHERE {base} ORDER BY 1")],
    }
    by_person = [dict(r) for r in cl.execute(text(f"""SELECT lower(l.username) AS username, count(*) AS n FROM {T} l
                                                        WHERE {where} GROUP BY 1 ORDER BY 2 DESC LIMIT 20"""), p).mappings()]
    return {"entries": [_out(dict(r)) for r in rows], "total": total, "limit": limit, "offset": offset, "facets": facets,
            "by_person": by_person, "kinds": KINDS,
            "you": {"username": user.username.lower(), "super_admin": _is_super(user),
                    "model_admin_of": [{"id": str(m["guid"]), "name": m["name"]} for m in sc["models"]],
                    "sees": "every change" if sc["all"] else
                            ("your own changes and every change in the models you administer" if sc["models"] else "your own changes")}}


def _need_super(user, what: str) -> None:
    if not _is_super(user):
        raise EditError(f"Only a Super Admin {what} the change log.", 403)


def export(conn, user, f: dict | None, fmt: str = "csv", cl=None) -> tuple[bytes, str, str]:
    """Every row the filters select (Super Admin), as CSV or an Excel workbook."""
    _need_super(user, "exports")
    cl = cl if cl is not None else conn
    T = f"{schema()}.entries"
    where, p = _where(user, scope(conn, user), f or {})
    rows = [_out(dict(r)) for r in cl.execute(text(f"SELECT {COLS} FROM {T} l WHERE {where} ORDER BY l.at DESC, l.id DESC"),
                                                p).mappings()]
    head = ["When", "Model", "User", "Kind", "Action", "Item type", "Item", "Entity or relationship type", "Field", "Old value",
            "New value", "Summary", "Commit", "Commit message"]
    flat = []
    for r in rows:
        when = r["at"].isoformat(sep=" ", timespec="seconds") if isinstance(r["at"], (datetime, date)) else str(r["at"])
        base = [when, r["model_name"] or "", r["username"], r["kind_name"], r["action"], r["item_type"], r["item_name"] or "",
                r["entity_type"] or ""]
        for d in (r["details"] or [{"field": "", "old": None, "new": None}]):
            flat.append(base + [d.get("field") or "", "" if d.get("old") is None else d["old"], "" if d.get("new") is None else d["new"],
                                r["summary"], r.get("commit_number") or "", r.get("commit_message") or ""])
    stamp = datetime.now().strftime("%Y-%m-%d")
    if fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Change log"
        ws.append(head)
        for c in ws[1]:
            c.font, c.fill = Font(bold=True), PatternFill("solid", fgColor="DDE6F0")
        for row in flat:
            ws.append([str(x) if x is not None else "" for x in row])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col, w in zip("ABCDEFGHIJKLMN", (19, 28, 18, 11, 22, 16, 32, 20, 18, 30, 30, 60, 8, 40), strict=True):
            ws.column_dimensions[col].width = w
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), f"change-log-{stamp}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(head)
    w.writerows(flat)
    return ("﻿" + out.getvalue()).encode("utf-8"), f"change-log-{stamp}.csv", "text/csv; charset=utf-8"


def delete(conn, user, f: dict | None, cl=None) -> dict:
    """Deletes the rows the filters select (Super Admin; every row when no filter is given). The history, the History
    tab, roll back and the audit trail are untouched; the deletion is logged as a row of its own."""
    _need_super(user, "deletes")
    cl = cl if cl is not None else conn
    T = f"{schema()}.entries"
    f = f or {}
    where, p = _where(user, scope(conn, user), f)
    n = cl.execute(text(f"DELETE FROM {T} l WHERE {where}"), p).rowcount
    kept = {k: v for k, v in f.items() if v not in (None, "", False)}
    cl.execute(text(f"""INSERT INTO {T} (at, username, kind, action, item_type, item_name, details, source)
                         VALUES (now(), lower(:u), 'action', 'Deleted change log entries', 'Change log', :n, CAST(:d AS jsonb), 'api')"""),
                 {"u": user.username, "n": f"{n} entries",
                  "d": json.dumps([{"field": "Entries deleted", "old": None, "new": n}] +
                                  ([{"field": k.replace("_", " ").capitalize(), "old": None, "new": str(v)} for k, v in kept.items()]
                                   or [{"field": "Which", "old": None, "new": "every entry"}]))})
    return {"deleted": n, "note": f"{n} change log entries deleted. The history of every item, roll back and the audit trail are kept."}


if __name__ == "__main__":
    sys.exit(main())
